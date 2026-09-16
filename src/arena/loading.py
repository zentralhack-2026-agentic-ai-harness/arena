import importlib
import importlib.util
from pathlib import Path


def load(target: str):
    """Load an object from "package.module:Name" or "path/to/file.py:Name"."""
    location, sep, name = target.rpartition(":")
    if not sep or not location or not name:
        raise ValueError(f"expected 'module:Name' or 'file.py:Name', got {target!r}")

    if location.endswith(".py"):
        path = Path(location)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(location)

    return getattr(module, name)
