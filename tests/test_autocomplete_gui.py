from unittest.mock import patch

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPlainTextEdit

from expo_jbm329.gui.autocomplete.controller import SqlAutocompleteController
from expo_jbm329.gui.autocomplete.engine import SqlAutoCompleter
from expo_jbm329.gui.autocomplete.identifiers import quote_identifier
from expo_jbm329.gui.autocomplete.popup import SqlEditorAutoCompletePopup


@pytest.fixture
def editor(qt_app):
    return QPlainTextEdit()


@pytest.fixture
def completer():
    c = SqlAutoCompleter()
    schema = {
        "public": {
            "users": ["id", "username"],
        }
    }
    c.set_schema(schema)
    return c


@pytest.fixture
def controller(editor, completer):
    ctrl = SqlAutocompleteController(editor, completer)
    ctrl.install()
    return ctrl


def test_popup_initialization(editor):
    popup = SqlEditorAutoCompletePopup(editor)
    assert popup.editor == editor
    assert popup.windowFlags() & Qt.WindowType.ToolTip
    assert popup.isVisible() is False


def test_popup_show_suggestions(editor):
    popup = SqlEditorAutoCompletePopup(editor)
    suggestions = ["user1", "user2"]
    popup.show_suggestions(suggestions)

    assert popup.list.count() == 2
    assert popup.list.item(0).text() == "user1"
    assert popup.isVisible() is True
    assert popup.list.currentRow() == 0


def test_popup_navigation(editor):
    popup = SqlEditorAutoCompletePopup(editor)
    popup.show_suggestions(["a", "b", "c"])

    # Down
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    popup.handle_key(event)
    assert popup.list.currentRow() == 1

    # Up
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    popup.handle_key(event)
    assert popup.list.currentRow() == 0


def test_popup_escape_hides(editor):
    popup = SqlEditorAutoCompletePopup(editor)
    popup.show_suggestions(["a"])
    assert popup.isVisible()

    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    popup.handle_key(event)
    assert popup.isVisible() is False


def test_controller_extract_prefix(editor, controller):
    editor.setPlainText("SELECT id FROM users")
    # Place cursor at the end
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    prefix = controller._extract_prefix()
    assert prefix == "users"

    editor.setPlainText("SELECT public.")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    prefix = controller._extract_prefix()
    assert prefix == "public."


@patch("expo_jbm329.gui.autocomplete.controller.QTimer.singleShot")
def test_controller_handle_keypress_period(mock_timer, controller):
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Period, Qt.KeyboardModifier.NoModifier, ".")
    handled = controller._handle_keypress(event)

    assert handled is False  # Allow editor to receive the period
    mock_timer.assert_called_once()
    assert mock_timer.call_args[0][1] == controller._update_suggestions


def test_controller_update_suggestions(editor, controller):
    editor.setPlainText("SELECT u")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    controller._update_suggestions()

    assert controller.popup.isVisible()
    assert controller.popup.list.count() > 0
    # Should contain 'users' and 'username' from our fixture schema
    items = [controller.popup.list.item(i).text() for i in range(controller.popup.list.count())]
    assert "users" in items
    assert "username" in items


def test_popup_insert_selected(editor):
    editor.setPlainText("SELECT u")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    popup = SqlEditorAutoCompletePopup(editor)
    popup.show_suggestions(["users"])
    popup.list.setCurrentRow(0)

    popup._insert_selected()

    assert editor.toPlainText() == 'SELECT "users"'
    assert popup.isVisible() is False


def test_controller_force_suggestions(editor, controller):
    editor.setPlainText("SELECT ")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    # Mocking singleShot is easier for testing direct calls
    controller._force_suggestions_now()

    assert controller.popup.isVisible()
    # Should show all objects since prefix is empty
    # col_list (id, username) + tables (users) + schemas (public) = 4
    assert controller.popup.list.count() == 4


def set_editor_cursor(editor, before, after=""):
    editor.setPlainText(before + after)
    cursor = editor.textCursor()
    cursor.setPosition(len(before.encode("utf-16-le")) // 2)
    editor.setTextCursor(cursor)


def select_suggestion(controller, name):
    names = [controller.popup.list.item(i).text() for i in range(controller.popup.list.count())]
    controller.popup.list.setCurrentRow(names.index(name))
    return names


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        ("mssql", "[users]"),
        ("tsql", "[users]"),
        ("postgres", '"users"'),
        ("postgresql", '"users"'),
        ("mysql", "`users`"),
        ("mariadb", "`users`"),
        ("sqlite", '"users"'),
        ("duckdb", '"users"'),
        ("oracle", '"users"'),
        (None, '"users"'),
    ],
)
@pytest.mark.parametrize("accept", ["return", "enter", "tab", "mouse"])
def test_acceptance_quotes_only_inserted_name_with_plain_labels(editor, controller, dialect, expected, accept):
    controller.set_dialect(dialect)
    set_editor_cursor(editor, "SELECT public.us", " FROM public.users;")
    controller._update_suggestions()
    assert controller.popup.isVisible()
    assert select_suggestion(controller, "users") == ["users"]
    if accept == "mouse":
        rect = controller.popup.list.visualItemRect(controller.popup.list.currentItem())
        QTest.mouseClick(controller.popup.list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    else:
        key = {"return": Qt.Key.Key_Return, "enter": Qt.Key.Key_Enter, "tab": Qt.Key.Key_Tab}[accept]
        QTest.keyClick(editor, key)
    assert editor.toPlainText() == f"SELECT public.{expected} FROM public.users;"
    assert editor.textCursor().position() == len(f"SELECT public.{expected}")
    assert not controller.popup.isVisible()


@pytest.mark.parametrize("dialect", ["mssql", "postgres", "mysql", "sqlite", "duckdb", None])
@pytest.mark.parametrize("name", ["select", "MixedCase", "order details", "literal.dot", 'a]b"c`d', '"literal"', " a "])
def test_forced_completion_preserves_metadata_characters(editor, controller, qt_app, dialect, name):
    controller.set_schema({"public": {"users": [name]}})
    controller.set_dialect(dialect)
    set_editor_cursor(editor, "SELECT ")
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    qt_app.processEvents()
    assert name in select_suggestion(controller, name)
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == "SELECT " + quote_identifier(name, dialect)


@pytest.mark.parametrize("dialect", ["tsql", "postgres", "mysql", "sqlite", "duckdb", None])
@pytest.mark.parametrize("forced", [False, True])
def test_schema_table_column_chain(editor, controller, qt_app, dialect, forced):
    schema, table, column = "my schema.dot", "my table.dot", "column with space"
    controller.set_schema({schema: {table: [column]}})
    controller.set_dialect(dialect)
    set_editor_cursor(editor, "SELECT my")
    controller._update_suggestions()
    select_suggestion(controller, schema)
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    expected = "SELECT " + quote_identifier(schema, dialect)
    assert editor.toPlainText() == expected

    for name in [table, column]:
        QTest.keyClick(editor, Qt.Key.Key_Period)
        qt_app.processEvents()
        if forced:
            controller.popup.hide()
            QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
            qt_app.processEvents()
        assert controller.popup.isVisible()
        assert select_suggestion(controller, name) == [name]
        QTest.keyClick(editor, Qt.Key.Key_Return)
        expected += "." + quote_identifier(name, dialect)
        assert editor.toPlainText() == expected


@pytest.mark.parametrize(
    ("before", "after", "dialect", "expected"),
    [
        ("SELECT [dbo].[us", "] FROM t", "mssql", "SELECT [dbo].[users] FROM t"),
        ('SELECT "public"."us', '" FROM t', "postgres", 'SELECT "public"."users" FROM t'),
        ("SELECT `public`.`us", "` FROM t", "mysql", "SELECT `public`.`users` FROM t"),
        ('SELECT public."us', 'ers" FROM t', "postgres", 'SELECT public."users" FROM t'),
        ("SELECT public.us", "ers FROM t", "tsql", "SELECT public.[users] FROM t"),
        ("SELECT public.[us]", ", id FROM t", "tsql", "SELECT public.[users], id FROM t"),
        ('SELECT public."us', "", "tsql", "SELECT public.[users]"),
        ("SELECT public.[us", "", "postgres", 'SELECT public."users"'),
        ("SELECT u", "", None, 'SELECT "users"'),
    ],
)
def test_acceptance_replaces_existing_delimiters_and_suffix(editor, controller, before, after, dialect, expected):
    controller.set_schema({"dbo": {"users": []}, "public": {"users": []}})
    controller.set_dialect(dialect)
    set_editor_cursor(editor, before, after)
    controller._update_suggestions()
    select_suggestion(controller, "users")
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == expected
    editor.undo()
    assert editor.toPlainText() == before + after
    editor.redo()
    assert editor.toPlainText() == expected


@pytest.mark.parametrize("dialect", ["tsql", "postgres", "mysql", "sqlite", "duckdb"])
@pytest.mark.parametrize("forced", [False, True])
def test_quoted_alias_completion_after_non_bmp_text(editor, controller, dialect, forced):
    schema, table, alias, column = "😀 schema", "orders.with.dot", 'a.lias]"`', "😀 column"
    controller.set_schema({schema: {table: [column]}})
    controller.set_dialect(dialect)
    qualifier = quote_identifier(alias, dialect)
    before = f"SELECT '😀', {qualifier}."
    after = f" FROM {quote_identifier(schema, dialect)}.{quote_identifier(table, dialect)} AS {qualifier};"
    set_editor_cursor(editor, before, after)
    if forced:
        controller._force_suggestions_now()
    else:
        controller._update_suggestions()
    assert controller._extract_prefix() == qualifier + "."
    assert select_suggestion(controller, column) == [column]
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    expected_before = before + quote_identifier(column, dialect)
    assert editor.toPlainText() == expected_before + after
    assert editor.textCursor().position() == len(expected_before.encode("utf-16-le")) // 2


@pytest.mark.parametrize("old_dialect", ["tsql", "postgres", "mysql"])
@pytest.mark.parametrize("new_dialect", ["tsql", "postgres", "mysql", None])
def test_dialect_change_while_popup_is_open(editor, controller, old_dialect, new_dialect):
    set_editor_cursor(editor, "SELECT us")
    controller.set_dialect(old_dialect)
    controller._update_suggestions()
    select_suggestion(controller, "users")
    controller.set_dialect(new_dialect)
    assert controller.popup.isVisible()
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == "SELECT " + quote_identifier("users", new_dialect)


def test_live_filtering_inside_quotes_preserves_spaces_and_delimiters(editor, controller, qt_app):
    controller.set_schema({"public": {"users": ["order details", "order date", "other"]}})
    controller.set_dialect("postgres")
    set_editor_cursor(editor, 'SELECT "order')
    controller._update_suggestions()
    assert select_suggestion(controller, "order details") == ["order date", "order details"]
    QTest.keyClick(editor, Qt.Key.Key_Space)
    qt_app.processEvents()
    assert controller._extract_prefix() == '"order '
    assert controller.popup.isVisible()
    QTest.keyClicks(editor, "de")
    qt_app.processEvents()
    assert select_suggestion(controller, "order details") == ["order details"]
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == 'SELECT "order details"'


def test_live_filtering_hides_popup_after_unquoted_space(editor, controller, qt_app):
    set_editor_cursor(editor, "SELECT u")
    controller._update_suggestions()
    QTest.keyClick(editor, Qt.Key.Key_Space)
    qt_app.processEvents()
    assert not controller.popup.isVisible()


@pytest.mark.parametrize(
    ("dialect", "before", "typed", "name", "expected"),
    [
        ("tsql", "SELECT [a", "]]", "a]b", "SELECT [a]]b]"),
        ("postgres", 'SELECT "a', '""', 'a"b', 'SELECT "a""b"'),
        ("mysql", "SELECT `a", "``", "a`b", "SELECT `a``b`"),
    ],
)
def test_live_filtering_with_escaped_delimiters(editor, controller, qt_app, dialect, before, typed, name, expected):
    controller.set_schema({"public": {"users": [name, "another"]}})
    controller.set_dialect(dialect)
    set_editor_cursor(editor, before)
    controller._update_suggestions()
    QTest.keyClicks(editor, typed)
    qt_app.processEvents()
    assert select_suggestion(controller, name) == [name]
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == expected


def test_insertion_is_one_undo_step_separate_from_typing(editor, controller, qt_app):
    set_editor_cursor(editor, "SELECT ")
    QTest.keyClicks(editor, "us")
    controller._update_suggestions()
    select_suggestion(controller, "users")
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    qt_app.processEvents()
    assert editor.toPlainText() == 'SELECT "users"'
    editor.undo()
    assert editor.toPlainText() == "SELECT us"
    editor.redo()
    assert editor.toPlainText() == 'SELECT "users"'


@pytest.mark.parametrize("before", ["SELECT 'us", "SELECT -- us", "SELECT /* us"])
def test_completion_and_stale_acceptance_do_not_insert_in_literals_or_comments(editor, controller, before):
    set_editor_cursor(editor, before)
    assert controller._extract_prefix() is None
    controller._force_suggestions_now()
    assert not controller.popup.isVisible()
    controller._update_suggestions()
    assert not controller.popup.isVisible()
    controller.popup.show_suggestions(["users"])
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == before
    assert not controller.popup.isVisible()
