"""Referee side of running strategies in separate processes.

In-process, a strategy shares the interpreter with the game: it can reach the live game
through gc or stack frames, patch classes, hang the run or exit it. Isolated, each strategy
runs in a fresh worker process (see worker.py) per match. It only ever sees observations and
only ever returns a Python literal, and every turn is under a time limit.

Not covered here, by design: file system and network access (run the tournament in a
container with no network), and signals: workers of one match share a uid, so a strategy
could kill the other worker or the referee. Separate uids per seat would close that.
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
    """Runs the strategy in a worker process. The process starts on construction."""

    def __init__(
        self,
        target: str,
        player_id: int,
        limits: Limits,
        python: str | None = None,
        sys_path: list[str] | None = None,
    ) -> None:
        self.player_id = player_id
        self.limits = limits
        config = {
            "target": target,
            "player_id": player_id,
            "sys_path": sys_path or [],
            "memory_mb": limits.memory_mb,
        }
        self._stderr = tempfile.TemporaryFile()
        self._cwd = tempfile.TemporaryDirectory(prefix="arena-worker-")
        self.proc = subprocess.Popen(
            [python or sys.executable, "-s", "-P", str(WORKER), json.dumps(config)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            cwd=self._cwd.name,
            env=_ENV,
            process_group=0,  # so close() also kills anything the strategy spawned
        )
        self._lines: queue.Queue[bytes | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self._deadline = 0.0

    def start(self) -> None:
        self._deadline = time.monotonic() + self.limits.init_timeout
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
        try:
            self.proc.stdin.write(text.encode() + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self._fail("crash", f"worker exited (code {self.proc.poll()})")

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
        self.proc.stdin.close()
        self.proc.stdout.close()
        self._stderr.close()
        self._cwd.cleanup()

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
