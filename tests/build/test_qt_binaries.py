from __future__ import annotations

import ast
from pathlib import Path

import pytest

from expo_jbm329.build.qt_binaries import filter_qt_binaries


@pytest.mark.parametrize(
    "source",
    [
        r"C:\venv\PyQt6\Qt6\plugins\sqldrivers\qsqlpsql.dll",
        r"C:\venv\PyQt6\Qt6\PLUGINS\SQLDRIVERS\qsqlite.dll",
        "/venv/PyQt6/Qt6/plugins/sqldrivers/libqsqlpsql.so",
        r"C:\venv\PyQt6\Qt6\plugins\sqldrivers\qsqloci.dll",
    ],
)
def test_sql_driver_plugins_are_excluded(source: str) -> None:
    assert filter_qt_binaries([(source, "plugins/sqldrivers")]) == []


def test_other_binaries_and_their_order_are_preserved() -> None:
    entries = [
        (r"C:\venv\PyQt6\Qt6\bin\Qt6Core.dll", "PyQt6/Qt6/bin"),
        (r"C:\venv\PyQt6\Qt6\plugins\platforms\qwindows.dll", "PyQt6/Qt6/plugins/platforms"),
        (r"C:\venv\PyQt6\Qt6\plugins\sqldrivers\qsqlpsql.dll", "PyQt6/Qt6/plugins/sqldrivers"),
        (r"C:\venv\PyQt6\Qt6\plugins\imageformats\qjpeg.dll", "PyQt6/Qt6/plugins/imageformats"),
        (r"C:\venv\postgres_driver\LIBPQ.dll", "postgres_driver"),
    ]

    assert filter_qt_binaries(iter(entries)) == entries[:2] + entries[3:]


def test_spec_filters_explicit_qt_collection_before_analysis() -> None:
    spec = Path(__file__).resolve().parents[2] / "expo.spec"
    tree = ast.parse(spec.read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "qt6_libs" for target in node.targets)
    )
    assert isinstance(assignment.value, ast.IfExp)
    call = assignment.value.body
    assert isinstance(call, ast.Call)
    assert isinstance(call.func, ast.Name) and call.func.id == "filter_qt_binaries"
    collection = call.args[0]
    assert isinstance(collection, ast.Call)
    assert isinstance(collection.func, ast.Name) and collection.func.id == "collect_dynamic_libs"
    analysis = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Analysis"
    )
    assert assignment.lineno < analysis.lineno
