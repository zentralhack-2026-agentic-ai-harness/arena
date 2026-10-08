"""Referee side of running strategies in separate processes.

In-process, a strategy shares the interpreter with the game: it can reach the live game
through gc or stack frames, patch classes, hang the run or exit it. Isolated, each strategy
runs in a fresh worker process (see worker.py) per match. It only ever sees observations and
only ever returns a Python literal, and every turn is under a time limit.

With `Limits.uid_base` (the referee must then run as root, with CAP_SETUID, CAP_SETGID and
CAP_KILL), every untrusted worker also runs under a uid of its own: it cannot signal the
referee or the other seat, read their /proc entries or write their files, and whatever it
leaves running is killed with it. The referee reads file targets and sends the source over
the pipe, so strategy files need not be readable by any worker.

Not covered here, by design: network access and what a worker can read on the file system.
Run the referee in a container with no network, and keep there what workers must not read
(other entrants, game source) unreadable to other users (see the README).
"""

import ast
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arena.worker import load

WORKER = Path(__file__).with_name("worker.py")

# Workers get this environment and nothing else: no secrets, no PYTHON* surprises.
_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "LANG": "C.UTF-8",
    "PYTHONHASHSEED": "0",
    "PYTHONDONTWRITEBYTECODE": "1",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}


@dataclass(frozen=True)
class Limits:
    turn_timeout: float = 1.0  # seconds per act() call, wall clock
    init_timeout: float = 10.0  # seconds for interpreter start, import and __init__
    memory_mb: int | None = 2048  # address space of the worker (RLIMIT_AS)
    max_reply_bytes: int = 1_000_000  # longest accepted repr(action)
    # Untrusted workers run as uid (and gid) uid_base + max_seats * slot + seat, so that every
    # seat of every concurrent match has a uid of its own; None: as the referee.
    uid_base: int | None = None
    max_seats: int = 8  # uids reserved per slot: the most players a match may have
    max_processes: int = 64  # per worker uid (RLIMIT_NPROC); only applies with uid_base


# This process's index among the processes that play matches in parallel (see
# arena.tournament.iter_matches), so that concurrent matches never share a worker uid.
_slot = 0


def set_slot(slot: int) -> None:
    global _slot
    _slot = slot


def seat_user(limits: Limits, player_id: int) -> int | None:
    """The uid an untrusted worker in seat `player_id` runs as, or None."""
    if limits.uid_base is None:
        return None
    if not 0 <= player_id < limits.max_seats:
        raise ValueError(f"seat {player_id} needs Limits.max_seats > {player_id}")
    return limits.uid_base + limits.max_seats * _slot + player_id


class StrategyFailure(Exception):
    """A strategy forfeits. `reason` is one of "exception", "timeout", "crash", "protocol"."""

    def __init__(self, player_id: int, reason: str, error: str) -> None:
        super().__init__(f"player {player_id}: {reason}")
        self.player_id = player_id
        self.reason = reason
        self.error = error


class InProcessPlayer:
    """Runs the strategy in the referee's interpreter. Fast, but only for trusted code."""

    def __init__(self, strategy: type | str, player_id: int) -> None:
        self._strategy = strategy  # class or target
        self.player_id = player_id
        self._obs: Any = None

    def start(self) -> None:
        self.strategy = self._call(self._instantiate)

    def send(self, obs: Any) -> None:
        self._obs = obs

    def receive(self) -> Any:
        return self._call(self.strategy.act, self._obs)

    def close(self) -> None:
        pass

    def _instantiate(self):
        cls = load(self._strategy) if isinstance(self._strategy, str) else self._strategy
        return cls(self.player_id)

    def _call(self, fn, *args):
        try:
            return fn(*args)
        except Exception:
            raise StrategyFailure(self.player_id, "exception", traceback.format_exc()) from None


class IsolatedPlayer:
    """Runs the strategy in a worker process. The process starts on construction.

    With `user`, the worker runs as that uid and gid, without supplementary groups; this
    process must then be root.
    """

    def __init__(
        self,
        target: str,
        player_id: int,
        limits: Limits,
        python: str | None = None,
        sys_path: list[str] | None = None,
        user: int | None = None,
    ) -> None:
        self.player_id = player_id
        self.limits = limits
        self.user = user
        self._source = _read_source(target, player_id)
        config = {
            "target": target,
            "player_id": player_id,
            "sys_path": sys_path or [],
            "memory_mb": limits.memory_mb,
            "max_processes": limits.max_processes if user is not None else None,
        }
        self._stderr = tempfile.TemporaryFile()
        self._cwd = tempfile.TemporaryDirectory(prefix="arena-worker-")
        os.chmod(self._cwd.name, 0o755)  # a worker of another uid may enter it, not write it
        self.proc = subprocess.Popen(
            [python or sys.executable, "-s", "-P", str(WORKER), json.dumps(config)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            cwd=self._cwd.name,
            env=_ENV,
            process_group=0,  # so close() also kills anything the strategy spawned
            **_as_user(user),
        )
        self._lines: queue.Queue[bytes | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self._deadline = 0.0

    def start(self) -> None:
        self._deadline = time.monotonic() + self.limits.init_timeout
        self._write(repr(self._source))
        tag, _ = self._next()
        if tag != "R":
            self._protocol_error(f"expected ready, got {tag!r}")

    def send(self, obs: Any) -> None:
        text = repr(obs)
        try:
            ast.literal_eval(text)
        except Exception as e:  # the game's fault, not the strategy's
            raise ValueError(f"observation is not a Python literal: {text[:200]}") from e
        self._deadline = time.monotonic() + self.limits.turn_timeout
        self._write(text)

    def receive(self) -> Any:
        tag, payload = self._next()
        if tag != "A":
            self._protocol_error(f"expected action, got {tag!r}")
        try:
            return ast.literal_eval(payload)
        except Exception:
            return None  # not a literal (e.g. np.int64(3)): the game sees a malformed action

    def close(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        self.proc.wait()
        if self.user is not None:  # also what the strategy detached from its process group
            _kill_user(self.user)
        self.proc.stdin.close()
        self.proc.stdout.close()
        self._stderr.close()
        self._cwd.cleanup()

    def _write(self, line: str) -> None:
        try:
            self.proc.stdin.write(line.encode() + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self._fail("crash", f"worker exited (code {self.proc.poll()})")

    def _read(self) -> None:
        stdout = self.proc.stdout
        try:
            while line := stdout.readline(self.limits.max_reply_bytes + 2):
                self._lines.put(line)
        except (OSError, ValueError):
            pass
        self._lines.put(None)

    def _next(self) -> tuple[str, str]:
        """Next message from the worker, as (tag, payload); raises StrategyFailure."""
        try:
            line = self._lines.get(timeout=max(0.0, self._deadline - time.monotonic()))
        except queue.Empty:
            self._fail("timeout", "no reply within the time limit")
        if line is None:
            try:
                self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            self._fail("crash", f"worker exited (code {self.proc.poll()})")
        if not line.endswith(b"\n"):
            if len(line) > self.limits.max_reply_bytes:
                self._protocol_error(f"reply longer than {self.limits.max_reply_bytes} bytes")
            self._fail("crash", "worker exited mid-reply")
        text = line[:-1].decode("utf-8", errors="replace")
        tag, payload = text[:1], text[1:]
        if tag == "E":
            self._fail("exception", ast.literal_eval(payload))
        return tag, payload

    def _protocol_error(self, message: str):
        self._fail("protocol", message)

    def _fail(self, reason: str, error: str):
        raise StrategyFailure(self.player_id, reason, f"{error}\n{self._stderr_tail()}".strip())

    def _stderr_tail(self, n: int = 4000) -> str:
        """Last n bytes of what the strategy wrote to stderr/stdout."""
        self._stderr.seek(0, os.SEEK_END)
        self._stderr.seek(max(0, self._stderr.tell() - n))
        tail = self._stderr.read().decode("utf-8", errors="replace")
        return f"--- worker output (tail) ---\n{tail}" if tail.strip() else ""


def _read_source(target: str, player_id: int) -> str | None:
    """The source of a file target, read here so that the worker needs no access to it."""
    location = target.rpartition(":")[0]
    if not location.endswith(".py"):
        return None  # a module target: the worker imports it
    try:
        return Path(location).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise StrategyFailure(player_id, "exception", traceback.format_exc()) from None


def _as_user(uid: int | None) -> dict:
    """Popen arguments that run the child as `uid`, with the same gid and no other groups."""
    return {} if uid is None else {"user": uid, "group": uid, "extra_groups": []}


def _kill_user(uid: int) -> None:
    """SIGKILL every process of `uid`: kill(-1) as that uid reaches exactly those."""
    subprocess.run(
        [sys.executable, "-I", "-S", "-c", "import os\ntry: os.kill(-1, 9)\nexcept OSError: pass"],
        env=_ENV,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        **_as_user(uid),
    )
