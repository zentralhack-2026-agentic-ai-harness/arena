# arena

The game interface and the match/tournament simulator. The games live in their own packages
(e.g. `arena-games-dev`), so installing `arena` never ships any game source.

## Use as a dependency

```bash
uv add git+https://github.com/<org>/arena
```

## Develop

Requires [uv](https://docs.astral.sh/uv/). Python 3.13 is pinned in `.python-version`.

```bash
uv sync          # creates .venv with arena (editable) + dev tools
uv run pytest
```

## The contract

Everything is in [`src/arena/core.py`](src/arena/core.py):

- **`Strategy`**: gets its `player_id` in `__init__` and implements `act(obs: dict) -> dict`.
  A fresh instance is created for every match.
- **`Game`**: `observe(player_id)`, `step(actions)`, `is_over()`, `scores()`. Two players,
  simultaneous moves. Illegal actions are no-ops.

Observations and actions are plain dicts. Their contents are defined by each game's `spec.md`.

If a strategy raises an exception, it forfeits the match.

Matches and tournaments take **entrants**: `Entrant(id, strategy_cls)`. Results are reported by
id, because submissions from different harnesses may share a class name. A bare strategy class
is accepted too and gets its class name as id.

## Running a tournament

```bash
uv run arena run --game arena_games_dev.alpha:AlphaGame \
              --strategies arena_games_dev.alpha.baselines:DoNothing \
                           team_a=a/strategy.py:Strategy team_b=b/strategy.py:Strategy \
              --seeds 10
```

Every entrant plays every other one in both seats, once per seed. Games and strategies are
referenced as `package.module:Name` or `path/to/file.py:Name`, optionally prefixed with `id=`
(the id defaults to the class name and must be unique).

From Python:

```python
from arena import Entrant, round_robin, summarize
from arena_games_dev.alpha import AlphaGame
from arena_games_dev.alpha.baselines import DoNothing

results = round_robin(AlphaGame, [DoNothing, Entrant("mine", MyBot)], seeds=range(10))
print(summarize(results))
```

`MatchResult.to_dict()` gives a JSON-serialisable record of a match.
