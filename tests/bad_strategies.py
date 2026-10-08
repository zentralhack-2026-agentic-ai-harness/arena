"""Misbehaving strategies for the isolation tests. Module-level so workers can import them."""

import gc
import os
import signal
import subprocess
import sys
import time

from arena.core import Strategy
from tests.dummy_game import DummyGame


class Sleeper(Strategy):
    def act(self, obs):
        time.sleep(30)


class SlowInit(Strategy):
    def __init__(self, player_id):
        super().__init__(player_id)
        time.sleep(30)

    def act(self, obs):
        return {"n": 9}


class InitCrash(Strategy):
    def __init__(self, player_id):
        raise RuntimeError("bad init")

    def act(self, obs):
        return {"n": 9}


class Exiter(Strategy):
    def act(self, obs):
        sys.exit(3)


class HardExiter(Strategy):
    def act(self, obs):
        os._exit(0)


class MemoryHog(Strategy):
    def act(self, obs):
        self.hoard = bytearray(8 * 2**30)
        return {"n": 9}


class Chatty(Strategy):
    """Prints a lot to stdout, which must not corrupt the protocol."""

    def act(self, obs):
        print("A{'n': 0}\n" * 1000)
        return {"n": 9}


class HugeReply(Strategy):
    def act(self, obs):
        return {"n": 9, "junk": "x" * 2_000_000}


class Cheater(Strategy):
    """Finds the live game through the garbage collector and hands itself points."""

    def act(self, obs):
        for obj in gc.get_objects():
            if isinstance(obj, DummyGame):
                obj._scores[self.player_id] += 100
        return {"n": 0}


class FakeInt:
    def __repr__(self) -> str:
        return "np.int64(3)"


class Echo(Strategy):
    """Returns obs["reply"], or something that is not a Python literal if obs["fake"]."""

    def act(self, obs):
        return FakeInt() if obs.get("fake") else obs["reply"]


class WhoAmI(Strategy):
    """Raises with the identity it runs under, so that the forfeit error shows it."""

    def __init__(self, player_id):
        raise RuntimeError(f"uid={os.getuid()} gid={os.getgid()} groups={os.getgroups()}")

    def act(self, obs):
        return {"n": 9}


class Intruder(Strategy):
    """Tries to kill the referee and every other worker, then plays on."""

    def __init__(self, player_id):
        super().__init__(player_id)
        for pid in [os.getppid(), *_other_workers()]:
            try:
                os.kill(pid, signal.SIGKILL)
            except (PermissionError, ProcessLookupError):
                pass

    def act(self, obs):
        return {"n": 9}


class Lingerer(Strategy):
    """Leaves a process behind, outside its process group."""

    def __init__(self, player_id):
        super().__init__(player_id)
        subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
        )

    def act(self, obs):
        return {"n": 9}


class Scribbler(Strategy):
    """Writes into its working directory."""

    def __init__(self, player_id):
        super().__init__(player_id)
        with open("scribble.txt", "w") as f:
            f.write("x")

    def act(self, obs):
        return {"n": 9}


def _other_workers() -> list[int]:
    pids = []
    for entry in os.listdir("/proc"):
        if entry.isdigit() and int(entry) != os.getpid():
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as f:
                    if b"worker.py" in f.read():
                        pids.append(int(entry))
            except OSError:
                pass
    return pids
