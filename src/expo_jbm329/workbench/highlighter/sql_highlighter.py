"""SQL syntax highlighting for the Expo workbench.

This module provides a Qt syntax highlighter for SQL text. Tokenization is
delegated to :mod:`sql_tokenizer`, which is dialect aware (quote styles,
comment prefixes, keyword sets) and never detects keywords inside strings,
comments or quoted identifiers. Optionally, known schema objects (tables,
views, schemas) and columns are highlighted with dedicated colors.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)

from expo_jbm329.workbench.highlighter.sql_dialect_rules import SqlDialectRules, rules_for_dialect
from expo_jbm329.workbench.highlighter.sql_tokenizer import (
    STATE_IN_BLOCK_COMMENT,
    STATE_IN_STRING,
    STATE_NONE,
    SqlToken,
    TokenKind,
    tokenize_line,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


@dataclass(frozen=True)
class Theme:
    """Highlighter color palette (tweak per brand/theme)."""

    friendly_name: str
    # Core token colors (use default_factory because QColor is mutable)
    kw: QColor = field(default_factory=lambda: QColor("#0B6CAD"))  # Keywords
    func: QColor = field(default_factory=lambda: QColor("#7A3E9D"))  # Functions (COUNT, SUM)
    ident: QColor = field(default_factory=lambda: QColor("#333333"))  # Identifiers (fallback)
    string: QColor = field(default_factory=lambda: QColor("#AA5500"))  # String literals
    number: QColor = field(default_factory=lambda: QColor("#2B7A0B"))  # Numeric literals
    comment: QColor = field(default_factory=lambda: QColor("#888888"))  # Comments

    # Additional styling
    operator: QColor = field(default_factory=lambda: QColor("#005A5A"))  # Operators/symbols
    bracketed_ident: QColor = field(default_factory=lambda: QColor("#333333"))
    quoted_ident: QColor = field(default_factory=lambda: QColor("#2F4F4F"))

    # Schema-aware identifiers (known tables/views/schemas and columns)
    table_ident: QColor = field(default_factory=lambda: QColor("#267F99"))
    column_ident: QColor = field(default_factory=lambda: QColor("#001080"))

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

    _STATE_NONE = STATE_NONE
    _STATE_IN_BLOCK_COMMENT = STATE_IN_BLOCK_COMMENT
    _STATE_IN_STRING = STATE_IN_STRING

    def __init__(
        self,
        document: QTextDocument,
        *,
        theme: Theme,
        keywords: Sequence[str] | None = None,
        functions: Sequence[str] | None = None,
        dialect: str | None = None,
    ) -> None:
        """Initialize the SQL highlighter.

        Args:
            document: The document to highlight.
            theme: Theme used to construct text formats.
            keywords: Optional keywords overriding the dialect keyword set.
            functions: Optional function names overriding the dialect function set.
            dialect: Optional sqlglot dialect name (e.g. "tsql", "sqlite").
                None uses generic rules covering all supported dialects.
        """
        super().__init__(document)

        self._theme = theme
        self._build_formats(theme)

        self._dialect: str | None = dialect
        self._keyword_override: frozenset[str] | None = frozenset(kw.upper() for kw in keywords) if keywords else None
        self._function_override: frozenset[str] | None = (
            frozenset(fn.upper() for fn in functions) if functions else None
        )
        self._object_names: frozenset[str] = frozenset()
        self._column_names: frozenset[str] = frozenset()

        self._rules: SqlDialectRules = self._build_rules()
        self._keywords: tuple[str, ...] = tuple(sorted(self._rules.keywords))
        self._functions: tuple[str, ...] = tuple(sorted(self._rules.functions))

    # ---------------------- Public API -------------------------------- #
    @property
    def dialect(self) -> str | None:
        """Return the sqlglot dialect name used for highlighting, if any."""
        return self._dialect

    def set_keywords(self, keywords: Iterable[str]) -> None:
        """Replace the keyword set (overrides dialect keywords).

        Args:
            keywords: New SQL keywords to highlight.
        """
        self._keyword_override = frozenset(kw.upper() for kw in keywords)
        self._refresh_rules()
        self.rehighlight()

    def set_functions(self, functions: Iterable[str]) -> None:
        """Replace the function set (overrides dialect functions).

        Args:
            functions: New SQL function names to highlight.
        """
        self._function_override = frozenset(fn.upper() for fn in functions)
        self._refresh_rules()
        self.rehighlight()

    def set_dialect(self, dialect: str | None) -> None:
        """Switch the SQL dialect used for tokenization.

        Rehighlights only if the dialect actually changed.

        Args:
            dialect: sqlglot dialect name, or None for generic rules.
        """
        normalized = dialect.lower() if dialect else None
        if normalized == self._dialect:
            return
        self._dialect = normalized
        self._refresh_rules()
        self.rehighlight()

    def set_schema_names(self, objects: Iterable[str], columns: Iterable[str]) -> None:
        """Set known schema object and column names for schema-aware coloring.

        Matching is case-insensitive. Rehighlights only if the names changed.

        Args:
            objects: Table, view and schema names.
            columns: Column names.
        """
        object_names = frozenset(name.lower() for name in objects if name)
        column_names = frozenset(name.lower() for name in columns if name)
        if object_names == self._object_names and column_names == self._column_names:
            return
        self._object_names = object_names
        self._column_names = column_names
        self.rehighlight()

    def set_theme(self, theme: Theme) -> None:
        """Swap the theme and rehighlight the document.

        Args:
            theme: New theme to apply.
        """
        self._theme = theme
        self._build_formats(theme)
        self.rehighlight()

    # ---------------------- QSyntaxHighlighter ------------------------ #
    @override
    def highlightBlock(self, text: str | None) -> None:
        """Highlight one document block.

        Args:
            text: The current text block to highlight.
        """
        tokens, end_state = tokenize_line(text or "", self._rules, self.previousBlockState())
        self.setCurrentBlockState(end_state)
        for token in tokens:
            fmt = self._format_for(token)
            if fmt is not None and token.length > 0:
                self.setFormat(token.start, token.length, fmt)

    # ---------------------- Internals --------------------------------- #
    def _build_formats(self, theme: Theme) -> None:
        """Create text formats from a theme."""
        self._fmt_kw = _mk_format(theme.kw, bold=theme.kw_bold)
        self._fmt_func = _mk_format(theme.func, bold=theme.func_bold)
        self._fmt_ident = _mk_format(theme.ident)
        self._fmt_string = _mk_format(theme.string, bg=theme.string_bg)
        self._fmt_number = _mk_format(theme.number)
        self._fmt_comment = _mk_format(theme.comment, bg=theme.comment_bg, italic=True)
        self._fmt_operator = _mk_format(theme.operator)
        self._fmt_bracketed_ident = _mk_format(theme.bracketed_ident)
        self._fmt_quoted_ident = _mk_format(theme.quoted_ident)
        self._fmt_table_ident = _mk_format(theme.table_ident)
        self._fmt_column_ident = _mk_format(theme.column_ident)

    def _build_rules(self) -> SqlDialectRules:
        """Combine dialect rules with explicit keyword/function overrides."""
        rules = rules_for_dialect(self._dialect)
        if self._keyword_override is not None:
            rules = dataclasses.replace(rules, keywords=self._keyword_override)
        if self._function_override is not None:
            rules = dataclasses.replace(rules, functions=self._function_override)
        return rules

    def _refresh_rules(self) -> None:
        self._rules = self._build_rules()
        self._keywords = tuple(sorted(self._rules.keywords))
        self._functions = tuple(sorted(self._rules.functions))

    def _schema_format(self, token: SqlToken) -> QTextCharFormat | None:
        """Return the table/column format when the identifier is a known schema name."""
        name = token.name.lower()
        is_object = name in self._object_names
        is_column = name in self._column_names
        if is_object and (token.qualifier or not is_column):
            return self._fmt_table_ident
        if is_column:
            return self._fmt_column_ident
        return None

    def _format_for(self, token: SqlToken) -> QTextCharFormat | None:
        """Map a token to its text format."""
        match token.kind:
            case TokenKind.KEYWORD:
                return self._fmt_kw
            case TokenKind.FUNCTION:
                return self._fmt_func
            case TokenKind.STRING:
                return self._fmt_string
            case TokenKind.NUMBER:
                return self._fmt_number
            case TokenKind.COMMENT:
                return self._fmt_comment
            case TokenKind.OPERATOR:
                return self._fmt_operator
            case TokenKind.QUOTED_IDENTIFIER:
                schema_fmt = self._schema_format(token)
                if schema_fmt is not None:
                    return schema_fmt
                return self._fmt_bracketed_ident if token.quote == "[" else self._fmt_quoted_ident
            case TokenKind.IDENTIFIER:
                return self._schema_format(token)
