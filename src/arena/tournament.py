import multiprocessing
import random
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from itertools import combinations

from arena.core import Entrant, Game, MatchResult, Strategy
from arena.isolation import Limits, set_slot
from arena.match import play_match


def tables(
    entrants: list[Entrant], n_players: int = 2, panel: list[Entrant] | None = None
) -> list[tuple[Entrant, ...]]:
    """The seatings of a tournament: every table, in every seat rotation (index = seat).

    Without a panel, every set of `n_players` distinct entrants is a table. With a panel,
    every entrant sits with every set of `n_players - 1` panel members, and no table seats two
    entrants. Either way no table seats the same entrant twice.

    Each table is played in its `n_players` cyclic rotations, so every member plays every seat
    once per table. For two seats these are both seats of every pairing.
    """
    if n_players < 1:
        raise ValueError(f"a table needs at least one seat, got n_players={n_players}")
    if panel is None:
        if len(entrants) < n_players:
            raise ValueError(f"{n_players} seats need at least {n_players} entrants")
        groups = [tuple(g) for g in combinations(entrants, n_players)]
    else:
        if len(panel) < n_players - 1:
            raise ValueError(f"{n_players} seats need a panel of at least {n_players - 1}")
        groups = [(e, *others) for e in entrants for others in combinations(panel, n_players - 1)]
    return [s for g in groups for s in rotations(g)]


def rotations(table: tuple[Entrant, ...]) -> list[tuple[Entrant, ...]]:
    """The cyclic seat rotations of a table, starting with the table itself."""
    return [table[r:] + table[:r] for r in range(len(table))]


def schedule(seatings: list[tuple[Entrant, ...]], seeds: list[int]) -> list[tuple]:
    """The matches to play, as (seating, seed), in rounds: one round per seed, in the order of
    `seeds`. A round plays every table once in each of its rotations; the tables of a round come
    in an order shuffled by its seed, the rotations of a table next to each other.

    So any prefix of the matches is a sequence of complete rounds plus part of one, and every
    table has played every seat equally often at the end of each round. The order is fixed by
    `seatings` and `seeds` alone.
    """
    groups: dict[frozenset, list] = {}
    for seating in seatings:
        groups.setdefault(frozenset(e.id for e in seating), []).append(seating)
    jobs = []
    for seed in seeds:
        order = list(groups.values())
        random.Random(seed).shuffle(order)
        jobs += [(seating, seed) for group in order for seating in group]
    return jobs


def iter_matches(
    game_cls: type[Game],
    seatings: list[tuple[Entrant, ...]],
    seeds: list[int],
    *,
    isolate: bool = False,
    limits: Limits | None = None,
    workers: int = 1,
) -> Iterator[MatchResult]:
    """Play every seating (see `tables`) once per seed and yield the results in a fixed order:
    in rounds, one per seed (see `schedule`).

    With `workers` > 1 the matches run in that many processes. The game class and the
    entrants' strategies must then be importable by name (module-level classes or targets).
    Each process gets its own slot, and with `limits.uid_base` its own worker uids.
    """
    jobs = schedule(seatings, seeds)
    play = partial(_play, game_cls, isolate=isolate, limits=limits)
    if workers <= 1:
        yield from map(play, jobs)
        return
    context = multiprocessing.get_context("spawn")  # no inherited threads or state
    slots = context.Value("i", 0)
    with ProcessPoolExecutor(
        max_workers=workers, mp_context=context, initializer=_take_slot, initargs=(slots,)
    ) as pool:
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
    """Every table of `game_cls.n_players` entrants (or, with `panel`, of one entrant and
    panel members) plays every seat rotation, once per seed; see `tables`. For two seats:
    every entrant plays every other one (or every panel member) in both seats.

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

    seatings = tables(entrants, getattr(game_cls, "n_players", 2), panel)
    return list(
        iter_matches(game_cls, seatings, seeds, isolate=isolate, limits=limits, workers=workers)
    )


def _take_slot(slots) -> None:
    with slots.get_lock():
        set_slot(slots.value)
        slots.value += 1


def _play(
    game_cls: type[Game],
    job: tuple[tuple[Entrant, ...], int],
    *,
    isolate: bool,
    limits: Limits | None,
) -> MatchResult:
    seating, seed = job
    return play_match(game_cls, list(seating), seed, isolate=isolate, limits=limits)


def summarize(results: list[MatchResult]) -> str:
    """Plain-text table per strategy: matches, total and mean revenue (its scores), its share
    of the revenue of all strategies, forfeits. Sorted by total revenue: what ranks, not wins."""
    stats: dict[str, dict] = {}
    for r in results:
        for seat, name in enumerate(r.players):
            s = stats.setdefault(name, {"n": 0, "revenue": 0.0, "F": 0})
            s["n"] += 1
            s["revenue"] += r.scores[seat]
            if (r.forfeit_turns or [None] * len(r.players))[seat] is not None or r.forfeit == seat:
                s["F"] += 1
    total = sum(s["revenue"] for s in stats.values())

    width = max([len("strategy")] + [len(name) for name in stats])
    lines = [
        f"{'strategy':<{width}}  {'matches':>7} {'revenue':>12} {'mean':>10} {'share':>7} {'F':>4}"
    ]
    for name, s in sorted(stats.items(), key=lambda kv: -kv[1]["revenue"]):
        share = s["revenue"] / total if total else 0.0
        lines.append(
            f"{name:<{width}}  {s['n']:>7} {s['revenue']:>12.2f} {s['revenue'] / s['n']:>10.2f}"
            f" {share:>6.1%} {s['F']:>4}"
        )
    return "\n".join(lines)
