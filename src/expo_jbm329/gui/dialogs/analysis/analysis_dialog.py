"""Advanced Analysis workspace dialog.

Lets the user pick a dataset and an analysis category from the sidebar.
Categories without a dedicated implementation yet show a placeholder
message (see the project's step-by-step Advanced Analysis plan); the
content panel itself is fully owned by the controller (AnalysisController),
which computes analyses in the background and swaps in the resulting view.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.services.analysis.categories import AnalysisCategory

if TYPE_CHECKING:
    from expo_jbm329.utils.dataset_ref import DatasetRef

_CATEGORY_ROLE = Qt.ItemDataRole.UserRole


class AnalysisDialog(QDialog):
    """Dialog hosting the Advanced Analysis workspace."""

    dataset_changed = pyqtSignal(str)  # dataset tab_id
    category_changed = pyqtSignal(str)  # AnalysisCategory value

    def __init__(
        self,
        *,
        parent: QWidget | None,
        datasets: list[DatasetRef],
        active_tab_id: str | None,
    ) -> None:
        """Initialize the Advanced Analysis dialog.

        Args:
            parent: Parent widget.
            datasets: Available datasets to analyze.
            active_tab_id: Initially selected dataset tab ID.
        """
        super().__init__(parent)

        self._datasets = datasets

        self.setWindowTitle(self.tr("Advanced Analysis"))
        self.resize(1100, 650)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        panels = QHBoxLayout()
        panels.setSpacing(12)

        left_panel = self._build_left_panel(active_tab_id)
        content_panel = self._build_content_panel()
        config_panel = self._build_config_panel()

        panels.addWidget(left_panel, 1)
        panels.addWidget(content_panel, 3)
        panels.addWidget(config_panel, 1)

        root.addLayout(panels, 1)
        root.addWidget(self._build_button_box())

        self._connect_signals()

        if self._dataset_combo.currentData():
            self.dataset_changed.emit(str(self._dataset_combo.currentData()))

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_left_panel(self, active_tab_id: str | None) -> QWidget:
        """Build the left panel with the dataset picker and category list."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        dataset_group = QGroupBox(self.tr("Dataset"), panel)
        dataset_form = QFormLayout(dataset_group)

        self._dataset_combo = QComboBox(dataset_group)
        for ds in self._datasets:
            label = f"{ds.title} ({ds.row_count} x {ds.column_count})"
            self._dataset_combo.addItem(label, ds.tab_id)

        if active_tab_id:
            self.select_dataset(active_tab_id)

        dataset_form.addRow(QLabel(self.tr("Dataset"), dataset_group), self._dataset_combo)

        category_group = QGroupBox(self.tr("Analysis"), panel)
        category_layout = QVBoxLayout(category_group)

        self._category_list = QListWidget(category_group)
        for category in AnalysisCategory:
            item = QListWidgetItem(self._category_label(category))
            item.setData(_CATEGORY_ROLE, category.value)
            self._category_list.addItem(item)

        # Overview is the natural starting point for exploring a dataset.
        self.select_category(AnalysisCategory.OVERVIEW)

        category_layout.addWidget(self._category_list)

        layout.addWidget(dataset_group)
        layout.addWidget(category_group, 1)

        return panel

    def _build_content_panel(self) -> QWidget:
        """Build the right-hand content/placeholder panel."""
        panel = QGroupBox(self.tr("Result"), self)
        self._content_panel = panel
        self._content_layout = QVBoxLayout(panel)
        self._content_widget: QWidget | None = None

        return panel

    def _build_config_panel(self) -> QWidget:
        """Build the configuration panel for the currently selected category.

        Hidden by default; categories with no configurable input (e.g.
        Overview) keep it hidden via `set_config_widget(None)`.
        """
        panel = QGroupBox(self.tr("Configuration"), self)
        self._config_panel = panel
        self._config_layout = QVBoxLayout(panel)
        self._config_widget: QWidget | None = None
        panel.setVisible(False)

        return panel

    def _build_button_box(self) -> QDialogButtonBox:
        """Build the bottom button box with a Close action."""
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        localize_dialog_buttons(buttons)
        return buttons

    def _connect_signals(self) -> None:
        """Wire internal widget signals to this dialog's public signals."""
        self._dataset_combo.currentIndexChanged.connect(self._on_dataset_index_changed)
        self._category_list.currentItemChanged.connect(self._on_category_item_changed)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_dataset_index_changed(self, _index: int) -> None:
        """Emit dataset_changed for the newly selected dataset."""
        tab_id = self._dataset_combo.currentData()
        if tab_id:
            self.dataset_changed.emit(str(tab_id))

    def _on_category_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        """Emit category_changed for the newly selected analysis category."""
        if current is None:
            return
        self.category_changed.emit(str(current.data(_CATEGORY_ROLE)))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_dataset_tab_id(self) -> str | None:
        """Return the currently selected dataset tab ID, if any."""
        data = self._dataset_combo.currentData()
        return str(data) if data else None

    def select_dataset(self, tab_id: str) -> None:
        """Select a dataset in the picker by tab ID.

        Args:
            tab_id: Stable internal tab ID to select.
        """
        for i in range(self._dataset_combo.count()):
            if self._dataset_combo.itemData(i) == tab_id:
                self._dataset_combo.setCurrentIndex(i)
                return

    def selected_category(self) -> AnalysisCategory | None:
        """Return the currently selected analysis category, if any."""
        item = self._category_list.currentItem()
        if item is None:
            return None
        return AnalysisCategory(item.data(_CATEGORY_ROLE))

    def select_category(self, category: AnalysisCategory) -> None:
        """Select an analysis category in the sidebar list.

        Args:
            category: Category to select.
        """
        for i in range(self._category_list.count()):
            item = self._category_list.item(i)
            if item is not None and item.data(_CATEGORY_ROLE) == category.value:
                self._category_list.setCurrentRow(i)
                return

    def show_placeholder(self, text: str) -> None:
        """Display a centered placeholder message in the content panel.

        Args:
            text: Message to show instead of analysis results.
        """
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.set_content_widget(label)

    def set_content_widget(self, widget: QWidget) -> None:
        """Replace the content panel's widget with the given widget.

        The previously displayed content widget, if any, is removed and
        scheduled for deletion.

        Args:
            widget: The widget to display in the content panel.
        """
        if self._content_widget is not None:
            self._content_layout.removeWidget(self._content_widget)
            self._content_widget.deleteLater()

        self._content_layout.addWidget(widget)
        self._content_widget = widget

    def content_widget(self) -> QWidget | None:
        """Return the widget currently displayed in the content panel."""
        return self._content_widget

    def content_panel(self) -> QWidget:
        """Return the stable result-pane container widget.

        Unlike `content_widget()` (which changes every time the analysis
        content is rebuilt), this returns the same container widget for the
        dialog's whole lifetime - suitable as a busy-overlay anchor.
        """
        return self._content_panel

    def set_config_widget(self, widget: QWidget | None) -> None:
        """Replace the configuration panel's widget, or hide it.

        Args:
            widget: The widget to display in the configuration panel, or
                `None` to hide the panel entirely (categories with no
                configurable input).
        """
        if self._config_widget is not None:
            self._config_layout.removeWidget(self._config_widget)
            self._config_widget.deleteLater()

        self._config_widget = widget

        if widget is None:
            self._config_panel.setVisible(False)
            return

        self._config_layout.addWidget(widget)
        self._config_panel.setVisible(True)

    def config_widget(self) -> QWidget | None:
        """Return the widget currently displayed in the configuration panel."""
        return self._config_widget

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def _category_label(self, category: AnalysisCategory) -> str:
        """Return the translated display label for an analysis category."""
        labels = {
            AnalysisCategory.OVERVIEW: self.tr("Overview"),
            AnalysisCategory.STATISTICS: self.tr("Statistics"),
            AnalysisCategory.HYPOTHESIS_TESTS: self.tr("Hypothesis Tests"),
            AnalysisCategory.CORRELATION: self.tr("Correlation"),
            AnalysisCategory.REGRESSION: self.tr("Regression"),
            AnalysisCategory.OUTLIERS: self.tr("Outliers"),
            AnalysisCategory.CLUSTERING: self.tr("Clustering"),
            AnalysisCategory.PCA: self.tr("PCA"),
            AnalysisCategory.TIME_SERIES: self.tr("Time Series"),
        }
        return labels[category]
