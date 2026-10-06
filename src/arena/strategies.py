"""Strategies that work for every game."""

from arena.core import Strategy


class Idle(Strategy):
    """Always returns None, which every game treats as a no-op (see Game.step)."""

    def act(self, obs):
        return None
