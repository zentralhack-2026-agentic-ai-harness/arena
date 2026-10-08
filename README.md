# arena

The game interface and the match/tournament simulator. The games live in their own packages
(e.g. [`arena-games-dev`](https://github.com/zentralhack-2026-agentic-ai-harness/arena-games-dev)),
so installing `arena` never ships any game source. `arena` itself has no runtime dependencies.

## Use as a dependency

```bash
uv add git+https://github.com/zentralhack-2026-agentic-ai-harness/arena
```

## Develop

Requires [uv](https://docs.astral.sh/uv/). Python 3.13 is pinned in `.python-version`.

```bash
uv sync          # creates .venv with arena (editable) + dev tools
uv run pytest
```

## The contract

Everything is in [`src/arena/core.py`](src/arena/core.py):

- **`Strategy`**: gets its `player_id` in `__init__` and implements `act(obs)`. A fresh instance
  is created for every match. Subclassing is optional: any class with that shape works.
- **`Game`**: `observe(player_id)`, `step(actions)`, `is_over()`, `scores()`. Two players,
  simultaneous moves. Illegal actions, including values the game cannot interpret, are no-ops.

Observations and actions are Python literals (dicts, lists, tuples, numbers, strings, bools,
`None`). Their contents are defined by each game's `spec.md`.

If a strategy raises an exception, it forfeits the match.

Matches and tournaments take **entrants**: `Entrant(id, strategy)`, where `strategy` is a class
or a target string (see below). Results are reported by id, because submissions from different
harnesses may share a class name. A bare class or target is accepted too and gets its class
name as id.

## Running a tournament

`arena` knows no games: a game is any importable `arena.Game`. Run tournaments from an
environment that has a games package installed, not from this repo. For the dev games that is
an [`arena-games-dev`](https://github.com/zentralhack-2026-agentic-ai-harness/arena-games-dev)
checkout (or any project that depends on it):

```bash
cd arena-games-dev
uv run arena run --game arena_games_dev.alpha:AlphaGame \
              --strategies arena_games_dev.alpha.baselines:DoNothing \
                           team_a=a/strategy.py:Strategy team_b=b/strategy.py:Strategy \
              --seeds 10
```

`a/strategy.py` and `b/strategy.py` stand for your own strategy files; relative paths resolve
against the current directory.

To try changes to `arena` against real games, run from the games checkout with your local
`arena` layered on top of the pinned one:

```bash
cd arena-games-dev
uv run --with-editable ../arena arena run --game arena_games_dev.alpha:AlphaGame ...
```

Every entrant plays every other one in both seats, once per seed. With `--panel X Y ...` the
strategies play only the panel members instead (and the panel members not each other).
`--workers N` plays N matches in parallel; results are the same, in the same order.

A game is referenced as a class (`package.module:Name`) or as a **game package**: a module that
exports `GAME` (the class), `BASELINES` (strategy classes) and `SPEC` (path to `spec.md`), e.g.
`arena_games_dev.alpha`. Strategies are referenced as `package.module:Name` or
`path/to/file.py:Name`, optionally prefixed with `id=` (the id defaults to the class name and
must be unique).

## Other commands

**`arena check`**: conformance. Plays the strategy, isolated, against `arena.strategies:Idle`
(always a no-op) in both seats. Passes if it never forfeits, which says nothing about how well
it plays. Exit code 0 or 1; `--json report.json` writes the full match records.

```bash
uv run arena check out/strategy.py:Strategy --game arena_games_dev.alpha
```

**`arena make-task`**: writes the task directory a harness receives: the game's `spec.md` and
a `task.json` with the contract (`strategy_file`, `strategy_class`) and the budget fields given.

```bash
uv run arena make-task --game arena_games_dev.alpha --out tasks/alpha \
              --budget-usd 1 --deadline-s 1800 --model gpt-5-nano
```

**`arena tournament job.json`**: a tournament described by a file, written one JSON line per
match to `--out` (default `matches.jsonl`) as matches finish. Relative strategy paths resolve
against the job file's directory. `panel`, `isolate` (default `true`), `limits` (fields of
`arena.Limits`) and `workers` are optional; without `panel` it is all-vs-all. An entry with
`"trusted": true` keeps the referee's uid under `limits.uid_base` (see Isolation).

```json
{
  "game": "arena_games_dev.alpha",
  "entrants": [
    {"id": "team_a", "strategy": "a/strategy.py:Strategy"},
    {"id": "team_b", "strategy": "b/strategy.py:Strategy", "python": "/venvs/b/bin/python"}
  ],
  "panel": [
    {"id": "spread", "strategy": "arena_games_dev.alpha.baselines:ProportionalSpread", "trusted": true}
  ],
  "seeds": [0, 1, 2, 3, 4],
  "limits": {"turn_timeout": 1.0, "uid_base": 1001},
  "workers": 8
}
```

From Python:

```python
from arena import Entrant, round_robin, summarize
from arena_games_dev.alpha import AlphaGame
from arena_games_dev.alpha.baselines import DoNothing

results = round_robin(AlphaGame, [DoNothing, Entrant("mine", MyBot)], seeds=range(10))
print(summarize(results))
```

`MatchResult.to_dict()` gives a JSON-serialisable record of a match. `round_robin(...,
panel=..., workers=...)` mirrors the CLI; `pairings` and `iter_matches` (results as they come)
are the building blocks.

## Isolation

In-process, a strategy shares the interpreter with the game and can reach it (via `gc`, stack
frames, monkeypatching), hang the run or exit it. So the CLI runs every strategy in its own
worker process per match, and `play_match` / `round_robin` do so with `isolate=True`:

- observations go to the worker as `repr()`, actions come back as `repr()` and are parsed with
  `ast.literal_eval`, so only Python literals cross: tuple/list and int/bool stay distinct, and
  a reply that is not a literal (e.g. `np.int64(3)`) reaches the game as `None`, a no-op;
- `Limits(turn_timeout, init_timeout, memory_mb, max_reply_bytes)` bound each worker; breaking
  one forfeits with `forfeit_reason` `"timeout"`, `"crash"` or `"protocol"` (a raised exception
  is `"exception"`);
- what a strategy prints goes to stderr and appears in the forfeit error, not in the protocol;
- `Entrant(id, target, python=...)` runs a worker under another interpreter, e.g. a venv with
  the strategy's own dependencies, or a bare Python where no game is importable. The worker
  (`arena/worker.py`) is standard-library only;
- the referee reads a file target and sends its source over the pipe, so the worker never
  needs read access to strategy files.

Games must therefore return observations that are Python literals, and treat any action they
cannot interpret (including `None`) as a no-op.

**Separate users.** With `Limits(uid_base=1001)` (`--uid-base 1001` for `run` and `check`,
`limits.uid_base` in a job file) every worker runs under a uid and gid of its own, without
supplementary groups: `uid_base + 2 * slot + seat`, where `slot` is the index of the process
playing the match (`--workers`), so no two live workers share a uid. A worker then cannot
signal the referee or the other seat, read their `/proc` entries or write their files, and
when the match ends every process of its uid is killed, also those it detached. A worker
may start at most `Limits.max_processes` processes. `Entrant(..., trusted=True)` (a
baseline) keeps the referee's uid. The referee must run as root, with `CAP_SETUID`,
`CAP_SETGID` and `CAP_KILL`; without them every isolated match raises `PermissionError`.

Network and file reads are not isolated by `arena`: run tournaments in a container without
network, in which what workers must not read (strategy files, game source) is not readable
by other users, and in which they have nowhere to write. `arena-eval`'s runner image does
exactly that. The tests for separate users need root; run them in a container:

```bash
docker run --rm -v "$PWD":/src:ro -v "$(command -v uv)":/bin/uv:ro \
  --cap-drop ALL --cap-add SETUID --cap-add SETGID --cap-add KILL python:3.13-slim \
  sh -c 'cp -r /src /app && cd /app && rm -rf .venv && UV_LINK_MODE=copy uv run pytest'
```
