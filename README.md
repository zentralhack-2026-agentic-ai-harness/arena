# arena

The game interface, the match/tournament simulator, and the dev games.

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

## Running a tournament

```bash
uv run arena run --game arena.games.alpha:AlphaGame \
              --strategies arena.games.alpha.baselines:DoNothing my_bot.py:MyBot \
              --seeds 10
```

Every strategy plays every other one in both seats, once per seed. Games and strategies are
referenced as `package.module:Name` or `path/to/file.py:Name`.

From Python:

```python
from arena import round_robin, summarize
from arena.games.alpha import AlphaGame
from arena.games.alpha.baselines import DoNothing

print(summarize(round_robin(AlphaGame, [DoNothing, MyBot], seeds=range(10))))
```

## Games

| game  | status |
|-------|--------|
| alpha | stub   |
