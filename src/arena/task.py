"""The task directory a harness receives: the game's spec.md and task.json."""

import json
import shutil
from pathlib import Path

from arena.pricing import load_prices

CONTRACT_VERSION = "0.2"  # 0.2: prices
STRATEGY_FILE = "strategy.py"  # what the harness must write into its output directory
STRATEGY_CLASS = "Strategy"  # the class that file must define


def make_task(
    spec: Path,
    out: Path,
    *,
    game_name: str,
    budget_usd: float | None = None,
    deadline_s: float | None = None,
    allowed_models: list[str] | None = None,
    prices: dict[str, dict[str, float]] | None = None,
) -> Path:
    """Write `out/spec.md` and `out/task.json`; return `out`.

    `prices`: USD per 1M tokens per model, {"model": {"input": .., "output": ..,
    "cached_input": .. (optional)}}; default: arena's table (arena/prices.json). Only the
    allowed models' prices are written, and every allowed model must have one.
    """
    prices = load_prices() if prices is None else prices
    if allowed_models is not None:
        unpriced = [m for m in allowed_models if m not in prices]
        if unpriced:
            raise ValueError(f"allowed models without a price: {unpriced}")
        prices = {m: prices[m] for m in allowed_models}
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(spec, out / "spec.md")
    task = {
        "contract_version": CONTRACT_VERSION,
        "game_name": game_name,
        "strategy_file": STRATEGY_FILE,
        "strategy_class": STRATEGY_CLASS,
        "budget_usd": budget_usd,
        "deadline_s": deadline_s,
        "allowed_models": allowed_models,
        "prices": prices,
    }
    (out / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    return out
