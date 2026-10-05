import argparse
import os
import sys

from arena.core import Entrant
from arena.loading import load
from arena.tournament import round_robin, summarize


def main() -> None:
    parser = argparse.ArgumentParser(prog="arena")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a round-robin tournament")
    run.add_argument("--game", required=True, help="e.g. arena_games_dev.alpha:AlphaGame")
    run.add_argument(
        "--strategies",
        nargs="+",
        required=True,
        help=(
            "at least two, each [id=]target, e.g. arena_games_dev.alpha.baselines:DoNothing "
            "team_a=a/strategy.py:Strategy team_b=b/strategy.py:Strategy "
            "(the id defaults to the class name)"
        ),
    )
    run.add_argument("--seeds", type=int, default=10, help="number of seeds per pairing")
    args = parser.parse_args()

    if len(args.strategies) < 2:
        parser.error("--strategies needs at least two entries")

    # Let "module:Name" targets resolve against the current directory.
    sys.path.insert(0, os.getcwd())

    game_cls = load(args.game)
    entrants = [_entrant(s) for s in args.strategies]
    results = round_robin(game_cls, entrants, seeds=list(range(args.seeds)))
    print(summarize(results))

    for r in results:
        if r.forfeit is not None:
            print(f"\nforfeit: {r.players[r.forfeit]} (seed {r.seed})\n{r.error}")
            break  # one traceback is enough to debug


def _entrant(arg: str) -> Entrant:
    """Parse "[id=]target"; the id defaults to the class name."""
    entrant_id, sep, target = arg.partition("=")
    if not sep:
        return Entrant.of(load(arg))
    return Entrant(entrant_id, load(target))


if __name__ == "__main__":
    main()
