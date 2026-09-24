"""The two interfaces every game and every strategy implements.

Observations and actions are plain dicts. What they contain is defined by
each game's spec.md, not by this module.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class Strategy(ABC):
    """A player. A fresh instance is created for every match."""

    def __init__(self, player_id: int) -> None:
        self.player_id = player_id

    @abstractmethod
    def act(self, obs: Any) -> Any:
        """Return this turn's action for the given observation."""


class Game(ABC):
    """A game with simultaneous moves."""

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed

    @abstractmethod
    def observe(self, player_id: int) -> dict:
        """Return what `player_id` can see right now."""

    @abstractmethod
    def step(self, actions: list[Any]) -> None:
        """Apply one action per player (index = player_id). Illegal actions are no-ops."""

    @abstractmethod
    def is_over(self) -> bool:
        """True once the game has ended."""

    @abstractmethod
    def scores(self) -> list[float]:
        """Cumulative score per player (index = player_id)."""


@dataclass
class MatchResult:
    players: list[str]  # strategy class names, by seat
    seed: int
    scores: list[float]
    turns: int
    forfeit: int | None = None  # seat whose strategy crashed
    error: str | None = None

    @property
    def winner(self) -> int | None:
        """Winning seat, or None for a draw. A forfeit loses regardless of score."""
        if self.forfeit is not None:
            return 1 - self.forfeit
        if self.scores[0] == self.scores[1]:
            return None
        return 0 if self.scores[0] > self.scores[1] else 1
