"""The task directory a harness receives: the game's spec.md and task.json."""

import json
import shutil
from pathlib import Path

CONTRACT_VERSION = "0.1"
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
) -> Path:
    """Write `out/spec.md` and `out/task.json`; return `out`."""
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
    }
    (out / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    return out
