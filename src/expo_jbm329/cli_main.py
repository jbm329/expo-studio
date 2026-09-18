"""Command-line entry point for the Expo application."""

from __future__ import annotations

import argparse


def cli_main() -> int:
    """Run the CLI entry point and return an exit code."""
    p = argparse.ArgumentParser("expo")
    p.add_argument("--version", action="store_true")
    args = p.parse_args()
    if args.version:
        print("Expo studio version 1.0.0")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
