from arena.core import Entrant, Game
from arena.isolation import Limits
from arena.match import play_match


def check_strategy(
    game_cls: type[Game],
    target: str,
    *,
    seeds: list[int] | None = None,
    limits: Limits | None = None,
    python: str | None = None,
) -> dict:
    """Play `target`, isolated, against an idle opponent in both seats, once per seed.

    The strategy conforms if it never forfeits. This says nothing about how well it plays.
    """
    candidate = Entrant("candidate", target, python=python)
    idle = Entrant("idle", "arena.strategies:Idle")
    results = [
        play_match(game_cls, seats, seed, isolate=True, limits=limits)
        for seed in seeds or [0]
        for seats in ([candidate, idle], [idle, candidate])
    ]
    failed = [r for r in results if r.forfeit is not None and r.players[r.forfeit] == "candidate"]
    return {
        "target": target,
        "passed": not failed,
        "matches": [r.to_dict() for r in results],
    }
