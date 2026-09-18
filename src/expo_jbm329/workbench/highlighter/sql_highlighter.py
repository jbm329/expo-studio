"""SQL syntax highlighting for the Expo workbench.

This module provides a Qt syntax highlighter for SQL text, including support
for keywords, functions, identifiers, numbers, operators, comments, and
multi-line string and block-comment highlighting.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import override

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)


@dataclass(frozen=True)
class Theme:
    """Highlighter color palette (tweak per brand/theme)."""
    friendly_name: str
    # Core token colors (use default_factory because QColor is mutable)
    kw: QColor = field(default_factory=lambda: QColor("#0B6CAD"))        # Keywords
    func: QColor = field(default_factory=lambda: QColor("#7A3E9D"))      # Functions (COUNT, SUM)
    ident: QColor = field(default_factory=lambda: QColor("#333333"))     # Identifiers (fallback)
    string: QColor = field(default_factory=lambda: QColor("#AA5500"))    # String literals
    number: QColor = field(default_factory=lambda: QColor("#2B7A0B"))    # Numeric literals
    comment: QColor = field(default_factory=lambda: QColor("#888888"))   # Comments

    # Additional styling
    operator: QColor = field(default_factory=lambda: QColor("#005A5A"))        # Operators/symbols
    bracketed_ident: QColor = field(default_factory=lambda: QColor("#333333"))
    quoted_ident: QColor = field(default_factory=lambda: QColor("#2F4F4F"))

    # Emphasis
    kw_bold: bool = True
    func_bold: bool = False

    # Background highlights (optional; transparent by default)
    string_bg: QColor = field(default_factory=lambda: QColor(0, 0, 0, 0))
    comment_bg: QColor = field(default_factory=lambda: QColor(0, 0, 0, 0))


def _mk_format(
    fg: QColor | None = None,
    *,
    bold: bool = False,
    bg: QColor | None = None,
    italic: bool = False,
) -> QTextCharFormat:
    """Create a QTextCharFormat with minimal allocations."""
    fmt = QTextCharFormat()
    if fg is not None:
        fmt.setForeground(QBrush(fg))
    if bg is not None:
        fmt.setBackground(QBrush(bg))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class SqlHighlighter(QSyntaxHighlighter):
    """Qt syntax highlighter for SQL text."""

    _STATE_NONE = 0
    _STATE_IN_BLOCK_COMMENT = 1
    _STATE_IN_STRING = 2

    def __init__(
        self,
        document: QTextDocument,
        *,
        theme: Theme,
        keywords: Sequence[str] | None = None,
        functions: Sequence[str] | None = None,
    ) -> None:
        """Initialize the SQL highlighter.

        Args:
            document: The document to highlight.
            theme: Theme used to construct text formats.
            keywords: Optional sequence of SQL keywords to highlight.
            functions: Optional sequence of SQL functions to highlight.
        """
        super().__init__(document)

        # ----- Theme & formats ------------------------------------------------
        self._theme = theme

        self._fmt_kw = _mk_format(theme.kw, bold=theme.kw_bold)
        self._fmt_func = _mk_format(theme.func, bold=theme.func_bold)
        self._fmt_ident = _mk_format(theme.ident)
        self._fmt_string = _mk_format(theme.string, bg=theme.string_bg)
        self._fmt_number = _mk_format(theme.number)
        self._fmt_comment = _mk_format(theme.comment, bg=theme.comment_bg, italic=True)
        self._fmt_operator = _mk_format(theme.operator)
        self._fmt_bracketed_ident = _mk_format(theme.bracketed_ident)
        self._fmt_quoted_ident = _mk_format(theme.quoted_ident)

        # ----- Token sets -----------------------------------------------------
        self._keywords = tuple(
            kw.upper()
            for kw in (
                keywords
                or ["SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "NULL", "LIKE", "ILIKE", "JOIN", "INNER", "LEFT",
                    "RIGHT", "FULL", "OUTER", "ON", "GROUP", "BY", "ORDER", "ASC", "DESC", "INSERT", "INTO", "VALUES",
                    "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "ALTER", "DROP", "VIEW", "INDEX", "CONSTRAINT",
                    "PRIMARY", "KEY", "FOREIGN", "DISTINCT", "TOP", "HAVING", "CASE", "WHEN", "THEN", "ELSE", "END",
                    "UNION", "ALL", "EXCEPT", "INTERSECT", "IS", "BETWEEN", "IN", "EXISTS", "OVER", "PARTITION",
                    "ROWS", "RANGE", "CAST", "CONVERT", "COALESCE", "NVL", "WITH", "AS", "MATERIALIZED", "RECURSIVE"]
            )
        )

        self._functions = tuple(
            fn.upper()
            for fn in (
                functions
                or ["COUNT", "SUM", "AVG", "MIN", "MAX", "LOWER", "UPPER", "SUBSTRING", "LEFT", "RIGHT", "LEN",
                    "LENGTH", "TRIM", "RTRIM", "LTRIM", "ROUND", "FLOOR", "CEILING", "ABS", "POWER", "GETDATE",
                    "CURRENT_TIMESTAMP", "NOW", "DATEADD", "DATEDIFF", "DATE_TRUNC"]
            )
        )

        # ----- Precompiled regex rules ---------------------------------------
        self._re_number = QRegularExpression(r"(?<![\w])(?:\d+\.\d+|\d+)(?![\w])")
        self._re_operator = QRegularExpression(r"[\+\-\*/=<>\.,;()\[\]]")
        self._re_line_comment = QRegularExpression(r"--[^\n]*")
        self._re_block_comment_start = QRegularExpression(r"/\*")
        self._re_block_comment_end = QRegularExpression(r"\*/")
        self._re_string_start = QRegularExpression(r"'")

        # Identifiers in [], "", ``
        self._re_bracketed_ident = QRegularExpression(r"\[[^\]]*\]")
        self._re_dquoted_ident = QRegularExpression(r'"[^"]*"')
        self._re_backtick_ident = QRegularExpression(r"`[^`]*`")

        # Build keyword/function regex as whole-word, case-insensitive
        self._re_keywords = [
            QRegularExpression(
                rf"\b{QRegularExpression.escape(kw)}\b",
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
            for kw in self._keywords
        ]
        self._re_functions = [
            QRegularExpression(
                rf"\b{QRegularExpression.escape(fn)}\s*(?=\()",
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
            for fn in self._functions
        ]

    # ---------------------- Public API -------------------------------- #
    def set_keywords(self, keywords: Iterable[str]) -> None:
        """Replace the keyword set and rebuild keyword regex patterns.

        Args:
            keywords: New SQL keywords to highlight.
        """
        self._keywords = tuple(kw.upper() for kw in keywords)
        self._re_keywords = [
            QRegularExpression(
                rf"\b{QRegularExpression.escape(kw)}\b",
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
            for kw in self._keywords
        ]
        self.rehighlight()

    def set_functions(self, functions: Iterable[str]) -> None:
        """Replace the function set and rebuild function regex patterns.

        Args:
            functions: New SQL function names to highlight.
        """
        self._functions = tuple(fn.upper() for fn in functions)
        self._re_functions = [
            QRegularExpression(
                rf"\b{QRegularExpression.escape(fn)}\s*(?=\()",
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
            for fn in self._functions
        ]
        self.rehighlight()

    def set_theme(self, theme: Theme) -> None:
        """Swap the theme and rehighlight the document.

        Args:
            theme: New theme to apply.
        """
        self._theme = theme
        self._fmt_kw = _mk_format(theme.kw, bold=theme.kw_bold)
        self._fmt_func = _mk_format(theme.func, bold=theme.func_bold)
        self._fmt_ident = _mk_format(theme.ident)
        self._fmt_string = _mk_format(theme.string, bg=theme.string_bg)
        self._fmt_number = _mk_format(theme.number)
        self._fmt_comment = _mk_format(theme.comment, bg=theme.comment_bg, italic=True)
        self._fmt_operator = _mk_format(theme.operator)
        self._fmt_bracketed_ident = _mk_format(theme.bracketed_ident)
        self._fmt_quoted_ident = _mk_format(theme.quoted_ident)
        self.rehighlight()

    # ---------------------- QSyntaxHighlighter ------------------------ #
    @override
    def highlightBlock(self, text: str) -> None:
        """Highlight one document block.

        Args:
            text: The current text block to highlight.
        """
        self.setCurrentBlockState(self._STATE_NONE)

        # 1) Continue multi-line constructs if needed
        if self.previousBlockState() == self._STATE_IN_BLOCK_COMMENT:
            self._apply_block_comment(text, continuing=True)
        elif self.previousBlockState() == self._STATE_IN_STRING:
            self._apply_multiline_string(text, continuing=True)

        # 2) Single-line primitives
        self._apply_regex_all(self._re_bracketed_ident, text, self._fmt_bracketed_ident)
        self._apply_regex_all(self._re_dquoted_ident, text, self._fmt_quoted_ident)
        self._apply_regex_all(self._re_backtick_ident, text, self._fmt_quoted_ident)
        self._apply_regex_all(self._re_number, text, self._fmt_number)
        self._apply_regex_all(self._re_operator, text, self._fmt_operator)

        # 3) Start multi-line constructs on this line
        self._apply_block_comment(text, continuing=False)
        self._apply_multiline_string(text, continuing=False)

        # 4) Keywords and functions last
        for rx in self._re_keywords:
            self._apply_regex_all(rx, text, self._fmt_kw)
        for rx in self._re_functions:
            self._apply_regex_all(rx, text, self._fmt_func)

        # 5) Comments
        self._apply_regex_all(self._re_line_comment, text, self._fmt_comment)

    # ---------------------- Internals --------------------------------- #
    def _apply_regex_all(self, rx: QRegularExpression, text: str, fmt: QTextCharFormat) -> None:
        """Apply a regex format to all matches in a text block.

        Args:
            rx: Regular expression used for matching.
            text: The text block to process.
            fmt: Text format to apply to matches.
        """
        it = rx.globalMatch(text)
        while it.hasNext():
            m = it.next()
            start = m.capturedStart()
            length = m.capturedLength()
            if start >= 0 and length > 0:
                self.setFormat(start, length, fmt)

    def _apply_block_comment(self, text: str, *, continuing: bool) -> None:
        """Highlight block comments and manage block state transitions.

        Args:
            text: The text block to process.
            continuing: Whether the previous block was already inside a block comment.
        """
        start_index = 0
        if continuing:
            end_match = self._re_block_comment_end.match(text, 0)
            if end_match.hasMatch():
                end_pos = end_match.capturedEnd()
                self.setFormat(0, end_pos, self._fmt_comment)
                start_index = end_pos
            else:
                self.setFormat(0, len(text), self._fmt_comment)
                self.setCurrentBlockState(self._STATE_IN_BLOCK_COMMENT)
                return

        while True:
            start_match = self._re_block_comment_start.match(text, start_index)
            if not start_match.hasMatch():
                break

            start_pos = start_match.capturedStart()
            end_match = self._re_block_comment_end.match(text, start_pos + 2)

            if end_match.hasMatch():
                end_pos = end_match.capturedEnd()
                self.setFormat(start_pos, end_pos - start_pos, self._fmt_comment)
                start_index = end_pos
            else:
                self.setFormat(start_pos, len(text) - start_pos, self._fmt_comment)
                self.setCurrentBlockState(self._STATE_IN_BLOCK_COMMENT)
                break

    def _apply_multiline_string(self, text: str, *, continuing: bool) -> None:
        """Highlight single-quoted strings across block boundaries.

        Args:
            text: The text block to process.
            continuing: Whether the previous block was already inside a string.
        """
        start_index = 0

        if continuing:
            end_pos = self._find_string_end(text, 0)
            if end_pos is not None:
                length = end_pos + 1
                self.setFormat(0, length, self._fmt_string)
                start_index = length
            else:
                self.setFormat(0, len(text), self._fmt_string)
                self.setCurrentBlockState(self._STATE_IN_STRING)
                return

        while True:
            start_match = self._re_string_start.match(text, start_index)
            if not start_match.hasMatch():
                break

            s_pos = start_match.capturedStart()
            end_pos = self._find_string_end(text, s_pos + 1)

            if end_pos is not None:
                self.setFormat(s_pos, (end_pos - s_pos) + 1, self._fmt_string)
                start_index = end_pos + 1
            else:
                self.setFormat(s_pos, len(text) - s_pos, self._fmt_string)
                self.setCurrentBlockState(self._STATE_IN_STRING)
                break

    @staticmethod
    def _find_string_end(text: str, start: int) -> int | None:
        """Find the end of a SQL single-quoted string.

        Handles doubled single quotes as escaped quotes.

        Args:
            text: The text block to scan.
            start: Index to start scanning from.

        Returns:
            The index of the closing quote, or None if no closing quote exists
            in the current block.
        """
        i = start
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "'":
                if (i + 1) < n and text[i + 1] == "'":
                    i += 2
                    continue
                return i
            i += 1
        return None
