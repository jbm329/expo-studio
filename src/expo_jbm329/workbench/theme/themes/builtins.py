# expo_jbm329/workbench/theme/themes/builtins.py

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
    quoted_ident=QColor("#A1A1A1"),
    kw_bold=True,
    func_bold=False,
)


