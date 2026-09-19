import os
from collections.abc import Iterable

root = ".."
ignore = {".git", ".idea", ".venv", "venv", "__pycache__", ".mypy_cache",
          ".pytest_cache", ".ruff_cache", "dist", "build", "node_modules"}


def walk(directory: str, prefix: str = "") -> None:
    try:
        entries: Iterable[str] = sorted(os.listdir(directory))
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return
    entries_list = list(entries)
    for i, name in enumerate(entries_list):
        if name in ignore or name.startswith(".DS_Store"):
            continue
        p = os.path.join(directory, name)
        connector = "└── " if i == len(entries_list) - 1 else "├── "
        print(prefix + connector + name)
        if os.path.isdir(p):
            walk(p, prefix + ("    " if i == len(entries_list) - 1 else "│   "))


walk(root)
