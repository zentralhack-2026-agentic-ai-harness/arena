# The loader lives in the worker, which must stay importable without arena.
from arena.worker import load

__all__ = ["load"]
