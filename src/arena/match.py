import sys
from pathlib import Path

from arena.core import Entrant, Game, MatchResult, Strategy
from arena.isolation import InProcessPlayer, IsolatedPlayer, Limits, StrategyFailure


def play_match(
    game_cls: type[Game],
    entrants: list[Entrant | type[Strategy] | str],
    seed: int,
    *,
    isolate: bool = False,
    limits: Limits | None = None,
) -> MatchResult:
    """Play one match. Seat index = player_id.

    Entrants may be given as bare strategy classes or targets; their class name is then the id.
    With `isolate`, every strategy runs in its own worker process under `limits` (see
    arena.isolation); without it, strategies share this interpreter and `limits` is ignored.

    A strategy that fails (raises; and when isolated: times out, crashes or breaks the
    protocol) forfeits and the match stops. Errors raised by the game itself are not caught:
    those are bugs in the game.
    """
    entrants = [Entrant.of(e) for e in entrants]
    game = game_cls(seed)
    result = MatchResult(players=[e.id for e in entrants], seed=seed, scores=[], turns=0)

    limits = limits or Limits()
    players = []
    try:
        for player_id, e in enumerate(entrants):  # isolated workers start booting here
            if isolate:
                players.append(_isolated_player(e, player_id, limits))
            else:
                players.append(InProcessPlayer(e.strategy, player_id))
        for player in players:
            player.start()
        while not game.is_over():
            for player_id, player in enumerate(players):
                player.send(game.observe(player_id))
            game.step([player.receive() for player in players])
            result.turns += 1
    except StrategyFailure as failure:
        result.forfeit = failure.player_id
        result.forfeit_reason = failure.reason
        result.error = failure.error
    finally:
        for player in players:
            player.close()

    result.scores = game.scores()
    return result


def _isolated_player(entrant: Entrant, player_id: int, limits: Limits) -> IsolatedPlayer:
    if isinstance(entrant.strategy, str):
        target = _absolute(entrant.strategy)
    elif entrant.python is not None:
        raise ValueError(f"entrant {entrant.id!r}: a custom interpreter needs a target string")
    else:
        target = _target_of(entrant.strategy)
    # With the referee's own interpreter, module targets resolve exactly as they do here.
    sys_path = None if entrant.python else [str(Path(p).resolve()) for p in sys.path]
    return IsolatedPlayer(target, player_id, limits, python=entrant.python, sys_path=sys_path)


def _target_of(cls: type) -> str:
    """The "module:QualName" target of a class the worker can import by name."""
    module = sys.modules.get(cls.__module__)
    spec = getattr(module, "__spec__", None)
    if spec is None or spec.name != cls.__module__ or "<locals>" in cls.__qualname__:
        raise ValueError(
            f"{cls.__qualname__} cannot be imported by name in a worker; "
            "pass a target string ('path/to/file.py:Name') instead"
        )
    return f"{cls.__module__}:{cls.__qualname__}"


def _absolute(target: str) -> str:
    """Resolve a file target against this directory: workers run in a scratch directory."""
    location, _, name = target.rpartition(":")
    return f"{Path(location).resolve()}:{name}" if location.endswith(".py") else target
