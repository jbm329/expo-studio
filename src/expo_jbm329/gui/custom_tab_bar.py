"""Custom tab bar with enhanced features.

This module provides a customized tab bar that supports theme-aware close
buttons, per-tab closability flags, and Swedish translations.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QIcon, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleOptionTab,
    QTabBar,
    QTabWidget,
    QToolButton,
)

if TYPE_CHECKING:
    from expo_jbm329.workbench.icon.icon_service import IconService


class TabBarProxyStyle(QProxyStyle):
    """OS-theme-aware tab bar style without stylesheets."""

    TAB_PADDING = 6
    RADIUS = 6
    INDICATOR_HEIGHT = 2

    # --------------------------------------------------
    # Spacing / padding
    # --------------------------------------------------
    @override
    def pixelMetric(self, metric: object, option: object=None, widget: object=None) -> object:
        """Custom pixelMetric override to provide consistent spacing."""
        if metric in (
            QStyle.PixelMetric.PM_TabBarTabHSpace,
            QStyle.PixelMetric.PM_TabBarTabVSpace,
        ):
            base = self.TAB_PADDING * 2

            # Wider padding for selected tab bold to prevent crowding
            if option is not None and hasattr(option, "state") and option.state & QStyle.StateFlag.State_Selected:
                return base + 4  # 2px per sida

            return base

        return super().pixelMetric(metric, option, widget)

    # --------------------------------------------------
    # Tab shape + background
    # --------------------------------------------------
    @override
    def drawControl(self, element: object, option: object, painter: object, widget: object=None) -> None:
        """Custom drawControl override for tab shape and background."""
        # Tab background / shape
        if (
            element == QStyle.ControlElement.CE_TabBarTabShape
            and isinstance(option, QStyleOptionTab)
            and isinstance(painter, QPainter)
            and isinstance(widget, QTabBar)
        ):
            self._draw_tab_shape(option, painter, widget)
            return

        super().drawControl(element, option, painter, widget)

    def _draw_tab_shape(self, option: QStyleOptionTab, painter: QPainter, widget: QTabBar) -> None:
        """Draw a rounded rectangle tab shape."""
        rect: QRect = option.rect
        palette = option.palette
        selected = option.state & QStyle.StateFlag.State_Selected

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg = palette.base().color() if selected else palette.window().color()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)

        radius = self.RADIUS

        round_left = True
        round_right = True

        if not selected:
            if option.position == QStyleOptionTab.TabPosition.Beginning:
                round_right = False
            elif option.position == QStyleOptionTab.TabPosition.End:
                round_left = False
            else:
                # Middle tab → inga rundade hörn
                round_left = False
                round_right = False

        path = QPainterPath()
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

        if round_left:
            path.moveTo(x + radius, y)
        else:
            path.moveTo(x, y)

        # top edge
        if round_right:
            path.lineTo(x + w - radius, y)
            path.quadTo(x + w, y, x + w, y + radius)
        else:
            path.lineTo(x + w, y)

        # right edge
        path.lineTo(x + w, y + h)

        # bottom edge
        path.lineTo(x, y + h)

        # left edge
        if round_left:
            path.lineTo(x, y + radius)
            path.quadTo(x, y, x + radius, y)
        else:
            path.lineTo(x, y)

        painter.drawPath(path)

        # Bottom indicator
        if selected:
            indicator = QRect(
                rect.left(),
                rect.bottom() - self.INDICATOR_HEIGHT + 1,
                rect.width(),
                self.INDICATOR_HEIGHT,
            )
            painter.fillRect(indicator, palette.highlight())

        if not selected and widget is not None:
            current = widget.currentIndex()
            index = option.tabIndex

            # Rita separator endast om denna tab inte ligger direkt till vänster om aktiv
            if index != current - 1:
                sep_color = palette.mid().color()
                painter.setPen(sep_color)
                painter.drawLine(
                    rect.topRight(),
                    rect.bottomRight(),
                )

        painter.restore()

    @override
    def drawPrimitive(self, element: object, option: object, painter: object, widget: object=None) -> None:
        """Custom drawPrimitive override for hover effects."""
        if option is None or painter is None:
            return

        if (
            element == QStyle.PrimitiveElement.PE_PanelButtonTool
            and isinstance(widget, QToolButton)
            and isinstance(widget.parent(), QTabBar)
        ):
            return

        if (
            element == QStyle.PrimitiveElement.PE_FrameTabBarBase
            and isinstance(widget, QTabBar)
            and isinstance(painter, QPainter)
        ):
            painter.save()
            color = option.palette.mid().color()
            painter.setPen(color)
            painter.drawLine(
                option.rect.bottomLeft(),
                option.rect.bottomRight(),
            )
            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)


class CustomTabBar(QTabBar):
    """Enterprise-grade tab bar with enhanced features.

    Features:
      - Close button supplied by IconService.
      - Automatic icon refresh on theme/icon updates.
      - Per-tab closable flags via tabData(i)["closable"].
      - HiDPI-aware button sizing.
      - Swedish tooltip.
      - Correct trailing-side placement (LTR/RTL).

    Attributes:
        CLOSE_BUTTON_SIZE: Fixed size for the close button.
        CLOSE_TOOLTIP: Tooltip text for the close button.
    """

    CLOSE_BUTTON_SIZE = 18
    CLOSE_TOOLTIP = "Stäng flik"

    def __init__(self, icon_service: IconService, parent: QTabWidget | None = None) -> None:
        """Initialize the custom tab bar.

        Args:
            icon_service: Service providing theme-aware icons.
            parent: Optional parent QTabWidget.
        """
        super().__init__(parent)

        self._icon_service = icon_service
        self._close_icon: QIcon = QIcon()

        # Style
        self.setStyle(TabBarProxyStyle(QApplication.style()))

        # Qt needs this to emit tabCloseRequested
        self.setTabsClosable(True)

        # Initial icon load
        self._reload_close_icon()

    # ----------------------------------------------------------------------
    # PUBLIC API (called by EditorServices when theme changes)
    # ----------------------------------------------------------------------
    def update_icons(self) -> None:
        """Reload icons from IconService and rebuild close buttons."""
        self._reload_close_icon()
        self.refresh_close_buttons()

    def refresh_close_buttons(self) -> None:
        """Recreate close buttons for all tabs."""
        for i in range(self.count()):
            self._install_close_button(i)

    # ----------------------------------------------------------------------
    # INTERNAL HELPERS
    # ----------------------------------------------------------------------
    def _reload_close_icon(self) -> None:
        """Load the theme-aware 'close' icon from IconService."""
        try:
            icon = self._icon_service.get("close")
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            icon = QIcon()

        if icon.isNull():
            # fallback
            style = self.style()
            if style is not None:
                icon = style.standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)

        self._close_icon = icon

    def _make_close_button(self) -> QToolButton:
        btn = QToolButton(self)

        btn.setAutoRaise(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.ArrowCursor)

        # Size + icon
        size = self.CLOSE_BUTTON_SIZE
        btn.setFixedSize(size, size)
        btn.setIconSize(btn.size())
        btn.setIcon(self._close_icon)

        btn.setToolTip(self.CLOSE_TOOLTIP)
        btn.setAccessibleName("close-tab-button")
        btn.setAccessibleDescription("Close the current tab")

        btn.clicked.connect(lambda: self._emit_close_for(btn))
        return btn

    def _install_close_button(self, index: int) -> None:
        """Attach close button if allowed."""
        if not (0 <= index < self.count()):
            return

        # Per-tab closable flag
        closable = True
        try:
            data = self.tabData(index)
            if isinstance(data, dict):
                closable = bool(data.get("closable", True))
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            pass

        pos = self._trailing_button_position()

        # Remove existing
        old = self.tabButton(index, pos)
        if old:
            self.setTabButton(index, pos, None)

        if closable:
            self.setTabButton(index, pos, self._make_close_button())

    def _trailing_button_position(self) -> QTabBar.ButtonPosition:
        """LTR = Right side, RTL = Left side."""
        return (
            QTabBar.ButtonPosition.LeftSide
            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft
            else QTabBar.ButtonPosition.RightSide
        )

    def _emit_close_for(self, btn: QToolButton) -> None:
        pos = self._trailing_button_position()
        for i in range(self.count()):
            if self.tabButton(i, pos) is btn:
                with contextlib.suppress(Exception):
                    self.tabCloseRequested.emit(i)
                return

    # ----------------------------------------------------------------------
    # OVERRIDES
    # ----------------------------------------------------------------------
    @override
    def tabInserted(self, index: int) -> None:
        """Called when a new tab is inserted.

        Installs the close button for the new tab.

        Args:
            index: The index of the inserted tab.
        """
        super().tabInserted(index)
        self._install_close_button(index)

    @override
    def tabMoved(self, from_index: int, to_index: int) -> None:
        """Called when a tab is moved.

        Updates the close buttons for the affected tabs.

        Args:
            from_index: The original index of the tab.
            to_index: The new index of the tab.
        """
        super().tabMoved(from_index, to_index)
        for i in (from_index, to_index):
            if 0 <= i < self.count():
                self._install_close_button(i)

    @override
    def tabRemoved(self, index: int) -> None:
        """Called when a tab is removed.

        Args:
            index: The index of the removed tab.
        """
        super().tabRemoved(index)
        # Qt cleans up automatically
