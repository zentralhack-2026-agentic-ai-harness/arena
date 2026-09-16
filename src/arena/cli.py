import argparse
import os
import sys

from arena.loading import load
from arena.tournament import round_robin, summarize


def main() -> None:
    parser = argparse.ArgumentParser(prog="arena")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a round-robin tournament")
    run.add_argument("--game", required=True, help="e.g. arena.games.alpha:AlphaGame")
    run.add_argument(
        "--strategies",
        nargs="+",
        required=True,
        help="at least two, e.g. arena.games.alpha.baselines:DoNothing my_bot.py:MyBot",
    )
    run.add_argument("--seeds", type=int, default=10, help="number of seeds per pairing")
    args = parser.parse_args()

    if len(args.strategies) < 2:
        parser.error("--strategies needs at least two entries")

    # Let "module:Name" targets resolve against the current directory.
    sys.path.insert(0, os.getcwd())

    game_cls = load(args.game)
    strategy_classes = [load(s) for s in args.strategies]
    results = round_robin(game_cls, strategy_classes, seeds=list(range(args.seeds)))
    print(summarize(results))

    for r in results:
        if r.forfeit is not None:
            print(f"\nforfeit: {r.players[r.forfeit]} (seed {r.seed})\n{r.error}")
            break  # one traceback is enough to debug


if __name__ == "__main__":
    main()
