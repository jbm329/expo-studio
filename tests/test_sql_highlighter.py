from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QPlainTextEdit

from expo_jbm329.workbench.highlighter.sql_highlighter import SqlHighlighter, Theme


@pytest.fixture
def theme():
    return Theme(friendly_name="TestTheme")


@pytest.fixture
def editor():
    return QPlainTextEdit()


@pytest.fixture
def highlighter(editor, theme):
    return SqlHighlighter(editor.document(), theme=theme)


def test_initial_state(highlighter):
    assert highlighter._theme.friendly_name == "TestTheme"
    assert len(highlighter._keywords) > 0
    assert len(highlighter._functions) > 0


def test_highlight_keywords(editor, highlighter):
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT * FROM table")

    # Check if setFormat was called for "SELECT" (0-6)
    # The first call might be for something else if we have multiple regexes.
    # Let's find the call that matches start=0 and length=6
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 0 and args[1] == 6:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.kw.name().upper()
            assert fmt.fontWeight() == QFont.Weight.Bold
            found = True
            break
    assert found, "setFormat not called for 'SELECT'"


def test_highlight_functions(editor, highlighter):
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT COUNT(*) FROM table")

    # COUNT is at position 7, length 5 (or 6 if it includes space before '(')
    # The regex is rf"\b{QRegularExpression.escape(fn)}\s*(?=\()"
    # For "COUNT(*)", it should match "COUNT" and maybe trailing space.
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 7 and args[1] >= 5:
            fmt = args[2]
            if fmt.foreground().color().name().upper() == highlighter._theme.func.name().upper():
                found = True
                break
    assert found, "setFormat not called for 'COUNT'"


def test_highlight_numbers(editor, highlighter):
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT 123, 45.67")

    # 123 at 7, len 3
    # 45.67 at 12, len 5
    matches = {7: 3, 12: 5}
    for start, length in matches.items():
        found = False
        for call in highlighter.setFormat.call_args_list:
            args, _ = call
            if args[0] == start and args[1] == length:
                fmt = args[2]
                if fmt.foreground().color().name().upper() == highlighter._theme.number.name().upper():
                    found = True
                    break
        assert found, f"setFormat not called for number at {start}"


def test_highlight_strings(editor, highlighter):
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT 'hello world'")

    # 'hello world' starts at 7, length 13
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 7 and args[1] == 13:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.string.name().upper()
            found = True
            break
    assert found, "setFormat not called for string"


def test_highlight_multiline_string(editor, highlighter):
    # Test starting a multiline string
    highlighter.setFormat = MagicMock()
    highlighter.setCurrentBlockState = MagicMock()
    highlighter.highlightBlock("SELECT 'line1")

    # Should highlight 'line1 to end of block
    # 'line1 starts at 7, length is 6
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 7 and args[1] == 6:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.string.name().upper()
            found = True
            break
    assert found
    # Should set state to IN_STRING (2)
    highlighter.setCurrentBlockState.assert_called_with(2)

    # Test continuing a multiline string
    highlighter.setFormat = MagicMock()
    highlighter.previousBlockState = MagicMock(return_value=2)
    highlighter.highlightBlock("line2'")

    # Should highlight from 0 to 6 (length of line2')
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 0 and args[1] == 6:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.string.name().upper()
            found = True
            break
    assert found


def test_highlight_comments(editor, highlighter):
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT -- line comment")

    # -- line comment starts at 7, length 15
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 7 and args[1] == 15:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.comment.name().upper()
            found = True
            break
    assert found


def test_highlight_block_comments(editor, highlighter):
    # Start block comment
    highlighter.setFormat = MagicMock()
    highlighter.setCurrentBlockState = MagicMock()
    highlighter.highlightBlock("SELECT /* comment")

    # /* comment starts at 7, length 10
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 7 and args[1] == 10:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.comment.name().upper()
            found = True
            break
    assert found
    # State should be IN_BLOCK_COMMENT (1)
    highlighter.setCurrentBlockState.assert_called_with(1)

    # End block comment
    highlighter.setFormat = MagicMock()
    highlighter.previousBlockState = MagicMock(return_value=1)
    highlighter.highlightBlock(" still comment */ 1")

    # Should highlight " still comment */" from 0 to 17
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 0 and args[1] == 17:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.comment.name().upper()
            found = True
            break
    assert found


def test_highlight_operators(editor, highlighter):
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("1 + 2 = 3")

    # + is at 2, = is at 6
    for pos in [2, 6]:
        found = False
        for call in highlighter.setFormat.call_args_list:
            args, _ = call
            if args[0] == pos and args[1] == 1:
                fmt = args[2]
                if fmt.foreground().color().name().upper() == highlighter._theme.operator.name().upper():
                    found = True
                    break
        assert found, f"Operator at {pos} not highlighted"


def test_highlight_quoted_idents(editor, highlighter):
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock('SELECT "column", [other], `backtick`')

    # "column" at 7, len 8
    # [other] at 17, len 7
    # `backtick` at 26, len 10
    expectations = {
        7: (8, highlighter._theme.quoted_ident),
        17: (7, highlighter._theme.bracketed_ident),
        26: (10, highlighter._theme.quoted_ident)
    }

    for pos, (length, color_theme) in expectations.items():
        found = False
        for call in highlighter.setFormat.call_args_list:
            args, _ = call
            if args[0] == pos and args[1] == length:
                fmt = args[2]
                if fmt.foreground().color().name().upper() == color_theme.name().upper():
                    found = True
                    break
        assert found, f"Ident at {pos} not highlighted correctly"


def test_set_keywords(highlighter, editor):
    highlighter.set_keywords(["CUSTOMKW"])
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT CUSTOMKW")

    # SELECT should NOT have the keyword format
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 0 and args[1] == 6:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() != highlighter._theme.kw.name().upper()

    # CUSTOMKW at 7, len 8
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 7 and args[1] == 8:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.kw.name().upper()
            found = True
            break
    assert found


def test_set_functions(highlighter, editor):
    highlighter.set_functions(["CUSTOMFUNC"])
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT CUSTOMFUNC()")

    # CUSTOMFUNC at 7, len 10 (regex matches trailing paren lookahead)
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 7 and args[1] >= 10:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.func.name().upper()
            found = True
            break
    assert found


def test_set_theme(highlighter, editor):
    new_theme = Theme(friendly_name="Dark", kw=QColor("#FF0000"))
    highlighter.set_theme(new_theme)
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT 1")

    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 0 and args[1] == 6:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == "#FF0000"
            found = True
            break
    assert found


def test_escaped_quotes_in_string(editor, highlighter):
    highlighter.setFormat = MagicMock()
    highlighter.highlightBlock("SELECT 'It''s a string'")

    # 'It''s a string' starts at 7, length 16
    found = False
    for call in highlighter.setFormat.call_args_list:
        args, _ = call
        if args[0] == 7 and args[1] == 16:
            fmt = args[2]
            assert fmt.foreground().color().name().upper() == highlighter._theme.string.name().upper()
            found = True
            break
    assert found
