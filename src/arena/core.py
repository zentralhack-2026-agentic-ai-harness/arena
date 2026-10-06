"""The two interfaces every game and every strategy implements.

Observations and actions are plain dicts. What they contain is defined by
each game's spec.md, not by this module.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
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
        """Return what `player_id` can see right now.

        Must be a Python literal (dicts, lists, tuples, str, int, float, bool, None), so that
        it can be sent to an isolated strategy.
        """

    @abstractmethod
    def step(self, actions: list[Any]) -> None:
        """Apply one action per player (index = player_id).

        Illegal actions are no-ops. This includes any value the game cannot interpret,
        e.g. None, which an isolated match passes for a reply that is not a Python literal.
        """

    @abstractmethod
    def is_over(self) -> bool:
        """True once the game has ended."""

    @abstractmethod
    def scores(self) -> list[float]:
        """Cumulative score per player (index = player_id)."""


@dataclass(frozen=True)
class Entrant:
    """A strategy entered into matches under a unique id.

    Results report the id, not the class name: submissions from different harnesses
    may well share a class name.

    `strategy` is a class or a target ("path/to/file.py:Name" or "package.module:Name").
    Isolated matches never load a target in the referee. `python` is the interpreter an
    isolated worker runs under (default: the referee's); it requires a target.
    """

    id: str
    strategy: "type[Strategy] | str"
    python: str | None = None

    @classmethod
    def of(cls, strategy: "Entrant | type[Strategy] | str") -> "Entrant":
        """Wrap a bare strategy class or target, using its class name as the id."""
        if isinstance(strategy, Entrant):
            return strategy
        if isinstance(strategy, str):
            return cls(strategy.rpartition(":")[2], strategy)
        return cls(strategy.__name__, strategy)


@dataclass
class MatchResult:
    players: list[str]  # entrant ids, by seat
    seed: int
    scores: list[float]
    turns: int
    forfeit: int | None = None  # seat whose strategy failed
    forfeit_reason: str | None = None  # "exception", "timeout", "crash" or "protocol"
    error: str | None = None

    @property
    def winner(self) -> int | None:
        """Winning seat, or None for a draw. A forfeit loses regardless of score."""
        if self.forfeit is not None:
            return 1 - self.forfeit
        if self.scores[0] == self.scores[1]:
            return None
        return 0 if self.scores[0] > self.scores[1] else 1

    def to_dict(self) -> dict:
        """JSON-serialisable form, including the derived winner."""
        return {**asdict(self), "winner": self.winner}
