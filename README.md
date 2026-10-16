# arena

The game interface and the match simulator. You never change or install it yourself:
[`arena-games-dev`](https://github.com/zentralhack-2026-agentic-ai-harness/arena-games-dev)
brings it in, and the `arena` commands below run from there.

## The contract

All of it is in [`src/arena/core.py`](src/arena/core.py). The rest of this repository (the
simulator, isolation, tournaments) is optional reading.

- **`Strategy`**: `__init__(self, player_id)` and `act(self, obs)`, which returns the turn's
  action. A fresh instance plays each match. Any class with that shape works; it need not
  import anything from arena.
- **`Game`**: `observe(player_id)`, `step(actions)`, `is_over()`, `scores()`. All players move
  at once. Each game's `spec.md` defines its observations, actions and scores.

What every game has in common:

- Observations and actions are Python literals: dicts, lists, tuples, numbers, strings,
  bools, `None`. Return plain values (`3`, not `numpy.int64(3)`): anything else reaches the
  game as `None`.
- An action the game cannot interpret, including `None`, does nothing.
- `act` has 1 second per call. If it raises or is too slow, the strategy forfeits: it plays
  `None` for the rest of the match, which still runs to the end, and it loses the match
  whatever the scores.
- Strategies run in a process of their own, with the standard library only. What they print
  goes to stderr, not to the game.

## Commands

From an `arena-games-dev` checkout:

```bash
# the task directory a harness receives (spec.md, task.json)
uv run arena make-task --game arena_games_dev.alpha --out tasks/alpha
# conformance: plays every seat against idle opponents, passes if it never forfeits
uv run arena check path/to/strategy.py:Strategy --game arena_games_dev.alpha
# play strategies against each other (or, with --panel, against a panel), every seat, N seeds
uv run arena run --game arena_games_dev.alpha --seeds 10 \
    --strategies mine=path/to/strategy.py:Strategy \
    --panel arena_games_dev.alpha.baselines:DoNothing
```

Strategies are given as `[name=]path/to/file.py:Class` or `package.module:Class`. See
`arena <command> --help` for the options.
