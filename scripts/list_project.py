import os
root = ".."
ignore = {".git", ".idea", ".venv", "venv", "__pycache__", ".mypy_cache",
          ".pytest_cache", ".ruff_cache", "dist", "build", "node_modules"}


def walk(d, prefix=""):
    try:
        entries = sorted(os.listdir(d))
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return
    for i, name in enumerate(entries):
        if name in ignore or name.startswith(".DS_Store"):
            continue
        p = os.path.join(d, name)
        connector = "└── " if i == len(entries)-1 else "├── "
        print(prefix + connector + name)
        if os.path.isdir(p):
            walk(p, prefix + ("    " if i == len(entries)-1 else "│   "))


walk(root)
