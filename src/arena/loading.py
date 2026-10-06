import importlib

# The loader lives in the worker, which must stay importable without arena.
from arena.worker import load

__all__ = ["load", "load_game", "load_game_package"]


def load_game(ref: str):
    """Load a game class from "package.module:Name", or from a game package's `GAME`."""
    return load(ref) if ":" in ref else load_game_package(ref).GAME


def load_game_package(ref: str):
    """Import a game package: a module exporting `GAME`, `BASELINES` and `SPEC`."""
    module = importlib.import_module(ref)
    missing = [name for name in ("GAME", "BASELINES", "SPEC") if not hasattr(module, name)]
    if missing:
        raise ValueError(f"{ref} is not a game package: it does not export {missing}")
    return module
