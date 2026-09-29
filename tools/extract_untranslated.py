#!/usr/bin/env python3
"""
Extract untranslated strings from a Qt Linguist .ts file.

Usage:
    python extract_untranslated.py path/to/file.ts
    python extract_untranslated.py path/to/file.ts -o untranslated.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def extract_untranslated(ts_file: Path) -> list[dict[str, str]]:
    """Extract unfinished translations from a Qt .ts file."""
    try:
        tree = ET.parse(ts_file)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML in '{ts_file}': {exc}") from exc

    root = tree.getroot()
    untranslated: list[dict[str, str]] = []

    for context in root.findall("context"):
        name_element = context.find("name")
        context_name = (
            name_element.text.strip()
            if name_element is not None and name_element.text
            else ""
        )

        for message in context.findall("message"):
            source_element = message.find("source")
            translation_element = message.find("translation")

            if source_element is None:
                continue

            source = source_element.text or ""

            if translation_element is None:
                continue

            translation_type = translation_element.get("type", "")

            # Qt Linguist marks untranslated messages as "unfinished".
            if translation_type != "unfinished":
                continue

            translation = translation_element.text or ""

            untranslated.append(
                {
                    "context": context_name,
                    "source": source,
                    "translation": translation,
                    "location": _get_location(message),
                }
            )

    return untranslated


def _get_location(message: ET.Element) -> str:
    """Return source-code location(s) associated with a message."""
    locations = []

    for location in message.findall("location"):
        filename = location.get("filename", "")
        line = location.get("line", "")

        if filename and line:
            locations.append(f"{filename}:{line}")
        elif filename:
            locations.append(filename)

    return "; ".join(locations)


def write_csv(
    output_file: Path,
    messages: list[dict[str, str]],
) -> None:
    """Write untranslated messages to CSV."""
    fieldnames = [
        "context",
        "source",
        "translation",
        "location",
    ]

    with output_file.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            quoting=csv.QUOTE_ALL,
        )

        writer.writeheader()
        writer.writerows(messages)


def main() -> int:
    """Run the command-line application."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract untranslated strings from a Qt Linguist "
            ".ts file and export them to CSV."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input .ts file.",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            "Path to the output CSV file. "
            "Defaults to '<input>_untranslated.csv'."
        ),
    )

    args = parser.parse_args()

    input_file: Path = args.input

    if not input_file.is_file():
        print(
            f"Error: file not found: {input_file}",
            file=sys.stderr,
        )
        return 1

    if input_file.suffix.lower() != ".ts":
        print(
            f"Error: input file must have a .ts extension: {input_file}",
            file=sys.stderr,
        )
        return 1

    output_file: Path = args.output or input_file.with_name(
        f"{input_file.stem}_untranslated.csv"
    )

    try:
        messages = extract_untranslated(input_file)
        write_csv(output_file, messages)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Input file:       {input_file}")
    print(f"Output file:      {output_file}")
    print(f"Untranslated:     {len(messages)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())