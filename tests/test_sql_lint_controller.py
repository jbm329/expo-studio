from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPoint, QEvent
from PyQt6.QtWidgets import QPlainTextEdit, QToolTip, QWidget

from expo_jbm329.db.sql_analysis import SqlDiagnostic
from expo_jbm329.gui.linting.sql_lint_controller import SqlLintController


class DummyBlock:
    def __init__(self, position: int, text: str, valid: bool = True) -> None:
        self._position = position
        self._text = text
        self._valid = valid

    def isValid(self) -> bool:
        return self._valid

    def position(self) -> int:
        return self._position

    def length(self) -> int:
        return len(self._text) + 1


class DummyDocument:
    def __init__(self, text: str) -> None:
        self._lines = text.splitlines() or [""]
        self._offsets: list[int] = []
        offset = 0
        for line in self._lines:
            self._offsets.append(offset)
            offset += len(line) + 1

    def findBlockByNumber(self, number: int) -> DummyBlock:
        if number < 0 or number >= len(self._lines):
            return DummyBlock(0, "", valid=False)
        return DummyBlock(self._offsets[number], self._lines[number])


class DummyViewport(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.installed = []
        self.removed = []

    def installEventFilter(self, obj: object) -> None:
        self.installed.append(obj)

    def removeEventFilter(self, obj: object) -> None:
        self.removed.append(obj)


class DummyEditor:
    def __init__(self, text: str = "SELECT 1") -> None:
        self._text = text
        self._document = DummyDocument(text)
        self._viewport = DummyViewport()
        self.textChanged = SimpleNamespace(connect=MagicMock(), disconnect=MagicMock())
        self.destroyed = SimpleNamespace(connect=MagicMock())
        self.extra_selections = None

    def viewport(self) -> DummyViewport:
        return self._viewport

    def document(self) -> DummyDocument:
        return self._document

    def toPlainText(self) -> str:
        return self._text

    def setPlainText(self, text: str) -> None:
        self._text = text
        self._document = DummyDocument(text)

    def setExtraSelections(self, selections) -> None:
        self.extra_selections = selections

@pytest.fixture
def editor() -> DummyEditor:
    return DummyEditor("SELECT 1")


@pytest.fixture
def controller(editor: DummyEditor) -> SqlLintController:
    return SqlLintController(editor, delay_ms=100)


def test_install_and_dispose(editor: DummyEditor):
    controller = SqlLintController(editor, delay_ms=100)

    controller.install()

    assert editor.textChanged.connect.called
    assert editor.destroyed.connect.called
    assert controller in editor.viewport().installed

    controller.dispose()

    assert editor.textChanged.disconnect.called
    assert controller in editor.viewport().removed
    assert controller._disposed is True


def test_set_dialect_schedules_lint(controller: SqlLintController):
    controller.schedule_lint = MagicMock()

    controller.set_dialect("sqlite")

    controller.schedule_lint.assert_called_once_with()


def test_run_lint_renders_diagnostics_and_publishes_status(editor: DummyEditor):
    controller = SqlLintController(editor, delay_ms=100, set_status=MagicMock())
    controller._render_diagnostics = MagicMock()
    controller._publish_status = MagicMock()
    controller._logger = MagicMock()
    controller._disposed = False
    editor.setPlainText("SELEC * FROM t")

    controller._run_lint()

    controller._render_diagnostics.assert_called_once()
    controller._publish_status.assert_called_once()
    assert controller._logger.debug.called


def test_run_lint_clears_empty_sql(editor: DummyEditor):
    controller = SqlLintController(editor, delay_ms=100)
    controller.clear_diagnostics = MagicMock()
    editor.setPlainText("   ")

    controller._run_lint()

    controller.clear_diagnostics.assert_called_once_with()


def test_publish_status_prefers_error_then_warning():
    editor = DummyEditor("SELECT 1")
    set_status = MagicMock()
    controller = SqlLintController(editor, delay_ms=100, set_status=set_status)

    controller._publish_status(
        [
            SqlDiagnostic(severity="warning", message="Warn", line=2, column=3),
            SqlDiagnostic(severity="error", message="Err", line=1, column=1),
        ]
    )

    set_status.assert_called_once_with("SQL error at line 1, column 1: Err", 10000)
