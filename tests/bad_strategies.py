"""Misbehaving strategies for the isolation tests. Module-level so workers can import them."""

import gc
import os
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
