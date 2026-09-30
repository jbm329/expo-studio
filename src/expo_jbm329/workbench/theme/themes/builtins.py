# expo_jbm329/workbench/theme/themes/builtins.py

"""Built-in highlighter themes shipped with Expo Studio."""

from __future__ import annotations

from PyQt6.QtGui import QColor

from expo_jbm329.workbench.highlighter.sql_highlighter import Theme

# ----------------------------------------
# BUILTIN LIGHT THEME
# ----------------------------------------
LIGHT_THEME = Theme(friendly_name="Light")

# ----------------------------------------
# BUILTIN DARK THEME
# ----------------------------------------
DARK_THEME = Theme(
    friendly_name="Dark",
    kw=QColor("#5AB0FF"),
    func=QColor("#C19CF3"),
    ident=QColor("#DDDDDD"),
    string=QColor("#E6B673"),
    number=QColor("#90EE90"),
    comment=QColor("#8B949E"),
    operator=QColor("#79C0FF"),
    bracketed_ident=QColor("#DDDDDD"),
    # Kept clearly distinct from the comment grey (#8B949E).
    quoted_ident=QColor("#D7BA7D"),
    table_ident=QColor("#4EC9B0"),
    column_ident=QColor("#9CDCFE"),
    kw_bold=True,
    func_bold=False,
)
