import sys
from pathlib import Path

from arena.core import Entrant, Game, MatchResult, Strategy
from arena.isolation import InProcessPlayer, IsolatedPlayer, Limits, StrategyFailure, seat_user


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
    protocol) forfeits: its score is frozen at that moment, and for the rest of the match its
    seat plays None (a no-op), so that the other seats still play, and score, to the end.
    `forfeit` is the first seat that failed. Errors raised by the game itself are not caught:
    those are bugs in the game.
    """
    entrants = [Entrant.of(e) for e in entrants]
    game = game_cls(seed)
    n = len(entrants)
    result = MatchResult(
        players=[e.id for e in entrants], seed=seed, scores=[], turns=0, forfeit_turns=[None] * n
    )
    frozen: dict[int, float] = {}  # seat -> its score when it failed

    def fail(failure: StrategyFailure) -> None:
        seat = failure.player_id
        frozen[seat] = game.scores()[seat]
        result.forfeit_turns[seat] = result.turns
        if result.forfeit is None:
            result.forfeit = seat
            result.forfeit_reason = failure.reason
            result.error = failure.error
        if players[seat] is not None:
            players[seat].close()
            players[seat] = None

    limits = limits or Limits()
    players: list = []
    try:
        for player_id, e in enumerate(entrants):  # isolated workers start booting here
            try:
                if isolate:
                    players.append(_isolated_player(e, player_id, limits))
                else:
                    players.append(InProcessPlayer(e.strategy, player_id))
            except StrategyFailure as failure:
                players.append(None)
                fail(failure)
        for player in players:
            _guard(player, fail, lambda p: p.start())
        while not game.is_over() and len(frozen) < n:
            for player_id, player in enumerate(players):
                _guard(player, fail, lambda p, i=player_id: p.send(game.observe(i)))
            actions = [_guard(player, fail, lambda p: p.receive()) for player in players]
            game.step(actions)
            result.turns += 1
    finally:
        for player in players:
            if player is not None:
                player.close()

    result.scores = [frozen.get(seat, score) for seat, score in enumerate(game.scores())]
    return result


def _guard(player, fail, call):
    """call(player) unless the seat has failed; None (a no-op) for a failed seat."""
    if player is None:
        return None
    try:
        return call(player)
    except StrategyFailure as failure:
        fail(failure)
        return None


def _isolated_player(entrant: Entrant, player_id: int, limits: Limits) -> IsolatedPlayer:
    if isinstance(entrant.strategy, str):
        target = _absolute(entrant.strategy)
    elif entrant.python is not None:
        raise ValueError(f"entrant {entrant.id!r}: a custom interpreter needs a target string")
    else:
        target = _target_of(entrant.strategy)
    # With the referee's own interpreter, module targets resolve exactly as they do here.
    sys_path = None if entrant.python else [str(Path(p).resolve()) for p in sys.path]
    user = None if entrant.trusted else seat_user(limits, player_id)
    return IsolatedPlayer(
        target, player_id, limits, python=entrant.python, sys_path=sys_path, user=user
    )


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
