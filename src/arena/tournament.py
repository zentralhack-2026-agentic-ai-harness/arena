from itertools import permutations

from arena.core import Game, MatchResult, Strategy
from arena.match import play_match


def round_robin(
    game_cls: type[Game], strategy_classes: list[type[Strategy]], seeds: list[int]
) -> list[MatchResult]:
    """Every strategy plays every other one, in both seats, once per seed."""
    return [
        play_match(game_cls, [a, b], seed)
        for a, b in permutations(strategy_classes, 2)
        for seed in seeds
    ]


def summarize(results: list[MatchResult]) -> str:
    """Plain-text table: wins / draws / losses / forfeits / mean score per strategy."""
    stats: dict[str, dict] = {}
    for r in results:
        for seat, name in enumerate(r.players):
            s = stats.setdefault(
                name, {"W": 0, "D": 0, "L": 0, "F": 0, "score": 0.0, "n": 0}
            )
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
