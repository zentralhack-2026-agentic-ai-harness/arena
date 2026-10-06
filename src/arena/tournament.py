import multiprocessing
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from itertools import permutations

from arena.core import Entrant, Game, MatchResult, Strategy
from arena.isolation import Limits
from arena.match import play_match


def pairings(
    entrants: list[Entrant], panel: list[Entrant] | None = None
) -> list[tuple[Entrant, Entrant]]:
    """Ordered (seat 0, seat 1) pairs: both seats of every pairing.

    Without a panel, every entrant meets every other one. With a panel, every entrant meets
    every panel member, and neither entrants nor panel members meet each other.
    """
    if panel is None:
        return list(permutations(entrants, 2))
    return [pair for e in entrants for p in panel for pair in ((e, p), (p, e))]


def iter_matches(
    game_cls: type[Game],
    pairs: list[tuple[Entrant, Entrant]],
    seeds: list[int],
    *,
    isolate: bool = False,
    limits: Limits | None = None,
    workers: int = 1,
) -> Iterator[MatchResult]:
    """Play every pair once per seed and yield the results in a fixed order.

    With `workers` > 1 the matches run in that many processes. The game class and the
    entrants' strategies must then be importable by name (module-level classes or targets).
    """
    jobs = [(a, b, seed) for a, b in pairs for seed in seeds]
    play = partial(_play, game_cls, isolate=isolate, limits=limits)
    if workers <= 1:
        yield from map(play, jobs)
        return
    context = multiprocessing.get_context("spawn")  # no inherited threads or state
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        yield from pool.map(play, jobs)


def round_robin(
    game_cls: type[Game],
    entrants: list[Entrant | type[Strategy] | str],
    seeds: list[int],
    *,
    panel: list[Entrant | type[Strategy] | str] | None = None,
    isolate: bool = False,
    limits: Limits | None = None,
    workers: int = 1,
) -> list[MatchResult]:
    """Every entrant plays every other one (or, with `panel`, every panel member) in both
    seats, once per seed.

    Entrants may be given as bare strategy classes or targets; their class name is then the
    id. Ids must be unique across entrants and panel. The keyword arguments are passed on to
    iter_matches.
    """
    entrants = [Entrant.of(e) for e in entrants]
    panel = None if panel is None else [Entrant.of(e) for e in panel]
    ids = [e.id for e in entrants + (panel or [])]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"entrant ids must be unique, got duplicates: {duplicates}")

    pairs = pairings(entrants, panel)
    return list(
        iter_matches(game_cls, pairs, seeds, isolate=isolate, limits=limits, workers=workers)
    )


def _play(
    game_cls: type[Game],
    job: tuple[Entrant, Entrant, int],
    *,
    isolate: bool,
    limits: Limits | None,
) -> MatchResult:
    a, b, seed = job
    return play_match(game_cls, [a, b], seed, isolate=isolate, limits=limits)


def summarize(results: list[MatchResult]) -> str:
    """Plain-text table: wins / draws / losses / forfeits / mean score per strategy."""
    stats: dict[str, dict] = {}
    for r in results:
        for seat, name in enumerate(r.players):
            s = stats.setdefault(name, {"W": 0, "D": 0, "L": 0, "F": 0, "score": 0.0, "n": 0})
            s["n"] += 1
            s["score"] += r.scores[seat]
            if r.forfeit == seat:
                s["F"] += 1
            if r.winner is None:
                s["D"] += 1
            elif r.winner == seat:
                s["W"] += 1
            else:
                s["L"] += 1

    width = max([len("strategy")] + [len(name) for name in stats])
    lines = [f"{'strategy':<{width}}  {'W':>4} {'D':>4} {'L':>4} {'F':>4} {'mean':>9}"]
    for name, s in sorted(stats.items(), key=lambda kv: -kv[1]["W"]):
        mean = s["score"] / s["n"]
        lines.append(
            f"{name:<{width}}  {s['W']:>4} {s['D']:>4} {s['L']:>4} {s['F']:>4} {mean:>9.2f}"
        )
    return "\n".join(lines)
