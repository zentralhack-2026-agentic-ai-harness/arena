import argparse
import json
import os
import sys
from pathlib import Path

from arena.conformance import check_strategy
from arena.core import Entrant, MatchResult
from arena.isolation import Limits
from arena.loading import load_game, load_game_package
from arena.task import make_task
from arena.tournament import iter_matches, pairings, round_robin, summarize

GAME_HELP = "game package (e.g. arena_games_dev.alpha) or class (e.g. ...alpha:AlphaGame)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arena")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a round-robin tournament")
    run.add_argument("--game", required=True, help=GAME_HELP)
    run.add_argument(
        "--strategies",
        nargs="+",
        required=True,
        help=(
            "each [id=]target, e.g. arena_games_dev.alpha.baselines:DoNothing "
            "team_a=a/strategy.py:Strategy team_b=b/strategy.py:Strategy "
            "(the id defaults to the class name)"
        ),
    )
    run.add_argument(
        "--panel",
        nargs="+",
        help="[id=]targets the strategies play instead of each other",
    )
    run.add_argument("--seeds", type=int, default=10, help="number of seeds per pairing")
    _add_execution_args(run)
    run.set_defaults(handler=_run)

    check = sub.add_parser("check", help="check that a strategy plays a game without forfeiting")
    check.add_argument("strategy", help="target, e.g. out/strategy.py:Strategy")
    check.add_argument("--game", required=True, help=GAME_HELP)
    check.add_argument("--seeds", type=int, default=1, help="number of seeds per seat")
    check.add_argument("--python", help="interpreter for the strategy (default: this one)")
    check.add_argument(
        "--turn-timeout", type=float, default=Limits.turn_timeout, help="seconds per turn"
    )
    _add_uid_base_arg(check)
    check.add_argument("--json", type=Path, help="also write the full report here")
    check.set_defaults(handler=_check)

    task = sub.add_parser("make-task", help="write the task directory a harness receives")
    task.add_argument("--game", required=True, help="game package, e.g. arena_games_dev.alpha")
    task.add_argument("--out", type=Path, required=True, help="directory to write")
    task.add_argument("--name", help="game name in task.json (default: last module part)")
    task.add_argument("--budget-usd", type=float)
    task.add_argument("--deadline-s", type=float)
    task.add_argument("--model", action="append", dest="models", help="allowed model; repeat")
    task.set_defaults(handler=_make_task)

    tournament = sub.add_parser("tournament", help="run a tournament described by a job file")
    tournament.add_argument("job", type=Path, help="job.json (see README)")
    tournament.add_argument(
        "--out", type=Path, default=Path("matches.jsonl"), help="one JSON line per match"
    )
    tournament.set_defaults(handler=_tournament)

    args = parser.parse_args(argv)

    # Let "module:Name" targets resolve against the current directory.
    sys.path.insert(0, os.getcwd())
    return args.handler(args) or 0


def _add_execution_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="run strategies in this interpreter: faster, but only for trusted code",
    )
    parser.add_argument(
        "--turn-timeout", type=float, default=Limits.turn_timeout, help="seconds per turn"
    )
    parser.add_argument("--workers", type=int, default=1, help="matches played in parallel")
    _add_uid_base_arg(parser)


def _add_uid_base_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--uid-base",
        type=int,
        help="run every worker under a uid of its own, from this one up (needs root)",
    )


def _run(args) -> None:
    entrants = [_entrant(s) for s in args.strategies]
    panel = None if args.panel is None else [_entrant(s) for s in args.panel]
    if panel is None and len(entrants) < 2:
        sys.exit("arena run: --strategies needs at least two entries (or use --panel)")

    results = round_robin(
        load_game(args.game),
        entrants,
        seeds=list(range(args.seeds)),
        panel=panel,
        isolate=not args.in_process,
        limits=Limits(turn_timeout=args.turn_timeout, uid_base=args.uid_base),
        workers=args.workers,
    )
    print(summarize(results))
    _print_first_forfeit(results)


def _check(args) -> int:
    report = check_strategy(
        load_game(args.game),
        args.strategy,
        seeds=list(range(args.seeds)),
        limits=Limits(turn_timeout=args.turn_timeout, uid_base=args.uid_base),
        python=args.python,
    )
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")

    for m in report["matches"]:
        seat = m["players"].index("candidate")
        status = "ok" if m["forfeit"] != seat else f"FORFEIT ({m['forfeit_reason']})"
        print(f"seed {m['seed']} seat {seat}: {status}, {m['turns']} turns")
    print("PASSED" if report["passed"] else "FAILED")
    if not report["passed"]:
        failed = next(m for m in report["matches"] if m["forfeit"] is not None)
        print(f"\n{failed['error']}")
    return 0 if report["passed"] else 1


def _make_task(args) -> None:
    package = load_game_package(args.game)
    out = make_task(
        Path(package.SPEC),
        args.out,
        game_name=args.name or args.game.rpartition(".")[2],
        budget_usd=args.budget_usd,
        deadline_s=args.deadline_s,
        allowed_models=args.models,
    )
    print(f"wrote {out / 'spec.md'} and {out / 'task.json'}")


def _tournament(args) -> None:
    job = json.loads(args.job.read_text())
    base = args.job.resolve().parent

    def entrant(e: dict) -> Entrant:
        return Entrant(
            e["id"],
            _resolve(e["strategy"], base),
            python=e.get("python"),
            trusted=e.get("trusted", False),
        )

    entrants = [entrant(e) for e in job["entrants"]]
    panel = [entrant(e) for e in job["panel"]] if job.get("panel") is not None else None
    ids = [e.id for e in entrants + (panel or [])]
    if len(set(ids)) != len(ids):
        sys.exit("arena tournament: entrant and panel ids must be unique")

    results = []
    with args.out.open("w") as out:
        for result in iter_matches(
            load_game(job["game"]),
            pairings(entrants, panel),
            job["seeds"],
            isolate=job.get("isolate", True),
            limits=Limits(**job.get("limits", {})),
            workers=job.get("workers", 1),
        ):
            out.write(json.dumps(result.to_dict()) + "\n")
            out.flush()
            results.append(result)
    print(summarize(results))
    print(f"\n{len(results)} matches written to {args.out}")


def _entrant(arg: str) -> Entrant:
    """Parse "[id=]target"; the id defaults to the class name.

    The target is not loaded here: isolated matches load it in the worker only.
    """
    entrant_id, sep, target = arg.partition("=")
    return Entrant(entrant_id, target) if sep else Entrant.of(arg)


def _resolve(target: str, base: Path) -> str:
    """Resolve a relative file target against `base`; module targets are left alone."""
    location, _, name = target.rpartition(":")
    if location.endswith(".py") and not Path(location).is_absolute():
        return f"{base / location}:{name}"
    return target


def _print_first_forfeit(results: list[MatchResult]) -> None:
    for r in results:
        if r.forfeit is not None:
            print(
                f"\nforfeit ({r.forfeit_reason}): {r.players[r.forfeit]} (seed {r.seed})\n{r.error}"
            )
            return  # one traceback is enough to debug


if __name__ == "__main__":
    sys.exit(main())
