"""Runs one strategy in its own process, on behalf of arena.isolation.

This file must stay standard-library only and must not import arena: it is started by path,
possibly under an interpreter that has nothing but the strategy's own dependencies.

    python -s -P worker.py '<config json>'

config: {"target": "file.py:Name" | "module:Name", "player_id": int,
         "sys_path": [str, ...], "memory_mb": int | null, "max_file_mb": int,
         "max_processes": int | null}

Protocol: one message per line on stdin/stdout. Values are encoded with repr() and decoded
with ast.literal_eval(), so only Python literals cross the boundary and tuple/list, int/bool
stay distinct.

    referee -> worker    repr(source | None)    once: a file target's source, read by the
                                                referee (None: import the module target)
    worker  -> referee   "R"                    strategy loaded and initialised
    referee -> worker    repr(obs)              once per turn
    worker  -> referee   "A" + repr(action)     the strategy's action
    worker  -> referee   "E" + repr(traceback)  the strategy raised; the worker exits
"""

import ast
import importlib
import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path


def load(target: str, source: str | None = None):
    """Load an object from "package.module:Name" or "path/to/file.py:Name".

    With `source`, a file target's code is taken from it instead of being read from the file.
    """
    location, sep, name = target.rpartition(":")
    if not sep or not location or not name:
        raise ValueError(f"expected 'module:Name' or 'file.py:Name', got {target!r}")

    if location.endswith(".py"):
        path = Path(location)
        spec = importlib.util.spec_from_file_location(path.stem, path)  # does not read it
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        if source is None:
            spec.loader.exec_module(module)
        else:
            exec(compile(source, str(path), "exec"), module.__dict__)
    else:
        module = importlib.import_module(location)

    obj = module
    for part in name.split("."):  # allows nested classes, e.g. "Outer.Inner"
        obj = getattr(obj, part)
    return obj


def _set_limits(memory_mb: int | None, max_file_mb: int, max_processes: int | None) -> None:
    try:
        import resource
    except ImportError:  # not POSIX: no limits
        return
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    file_bytes = max_file_mb * 2**20  # also caps what the strategy can print to stderr
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
    if memory_mb is not None:
        memory_bytes = memory_mb * 2**20
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    if max_processes is not None:  # counts per uid: only meaningful for a worker's own uid
        resource.setrlimit(resource.RLIMIT_NPROC, (max_processes, max_processes))


def main() -> None:
    config = json.loads(sys.argv[1])

    # The protocol owns the original stdout. Anything the strategy prints goes to stderr.
    channel = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)

    def send(tag: str, payload: str = "") -> None:
        channel.write(tag + payload + "\n")
        channel.flush()

    _set_limits(config.get("memory_mb"), config.get("max_file_mb", 16), config.get("max_processes"))
    sys.path[:0] = config.get("sys_path", [])
    source = ast.literal_eval(sys.stdin.readline())

    try:
        strategy = load(config["target"], source)(config["player_id"])
    except Exception:
        send("E", repr(traceback.format_exc()))
        return
    send("R")

    for line in sys.stdin:
        obs = ast.literal_eval(line)
        try:
            reply = repr(strategy.act(obs))
        except Exception:
            send("E", repr(traceback.format_exc()))
            return
        send("A", reply)


if __name__ == "__main__":
    main()
