"""Hypothesis Tests configuration widget (test selector + per-test column pickers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.analysis.chi_square_config import ChiSquareConfigWidget
from expo_jbm329.gui.dialogs.analysis.group_comparison_config import GroupComparisonConfigWidget
from expo_jbm329.services.analysis.categories import HypothesisTest

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.chi_square import ChiSquareResult
    from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult

# A test's (first, second) column pair, or None when unavailable/incomplete.
ColumnSelection = tuple[str, str] | None

_COLUMNS_PER_CHI_SQUARE_TEST = 2


class HypothesisTestsConfigWidget(QWidget):
    """Lets the user choose a hypothesis test and that test's columns.

    A "Test" selector sits above a stacked page per test; each page is the
    test's own configuration widget, or a short notice when the dataset
    has no eligible columns for that test. Every page is built once, so
    switching tests back and forth keeps each test's column picks.

    `configuration_changed` fires whenever the selected test or the active
    test's column selection changes; `AnalysisController` then recomputes
    the content pane from `selected_test()` and the matching selection.
    """

    configuration_changed = pyqtSignal()

    def __init__(
        self,
        group_comparison: GroupComparisonResult,
        chi_square: ChiSquareResult,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            group_comparison: Default Group Comparison result, used to
                populate that test's column pickers.
            chi_square: Default chi-square result, used to populate that
                test's column pickers.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._test_combo = QComboBox(self)
        self._test_combo.addItem(self.tr("Group comparison"), HypothesisTest.GROUP_COMPARISON.value)
        self._test_combo.addItem(self.tr("Chi-square independence"), HypothesisTest.CHI_SQUARE.value)

        form = QFormLayout()
        form.addRow(QLabel(self.tr("Test"), self), self._test_combo)
        layout.addLayout(form)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack)

        self._group_comparison_config: GroupComparisonConfigWidget | None = None
        if group_comparison.available_numeric_columns and group_comparison.available_grouping_columns:
            self._group_comparison_config = GroupComparisonConfigWidget(group_comparison, self._stack)
            self._group_comparison_config.selection_changed.connect(self._emit_configuration_changed)
            self._stack.addWidget(self._group_comparison_config)
        else:
            self._stack.addWidget(self._build_unavailable_label())

        self._chi_square_config: ChiSquareConfigWidget | None = None
        if len(chi_square.available_columns) >= _COLUMNS_PER_CHI_SQUARE_TEST:
            self._chi_square_config = ChiSquareConfigWidget(chi_square, self._stack)
            self._chi_square_config.selection_changed.connect(self._emit_configuration_changed)
            self._stack.addWidget(self._chi_square_config)
        else:
            self._stack.addWidget(self._build_unavailable_label())

        layout.addStretch(1)

        # Connected only after the initial population above, so setting up
        # the default test never emits a spurious first signal.
        self._test_combo.currentIndexChanged.connect(self._on_test_changed)

    def _build_unavailable_label(self) -> QLabel:
        """Build the page shown for a test the dataset has no eligible columns for."""
        label = QLabel(self.tr("This test is not available for the selected dataset."), self._stack)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    def _on_test_changed(self, index: int) -> None:
        """Show the selected test's page and announce the configuration change."""
        self._stack.setCurrentIndex(index)
        self.configuration_changed.emit()

    def _emit_configuration_changed(self, *_selection: str) -> None:
        """Forward a per-test selection change as a configuration change."""
        self.configuration_changed.emit()

    def selected_test(self) -> HypothesisTest:
        """Return the currently selected hypothesis test."""
        return HypothesisTest(self._test_combo.currentData())

    def group_comparison_selection(self) -> ColumnSelection:
        """Return the Group Comparison ``(numeric, grouping)`` selection, if available."""
        if self._group_comparison_config is None:
            return None
        return self._group_comparison_config.current_selection()

    def chi_square_selection(self) -> ColumnSelection:
        """Return the chi-square ``(row, column)`` selection, if available."""
        if self._chi_square_config is None:
            return None
        return self._chi_square_config.current_selection()

    def current_configuration(self) -> tuple[HypothesisTest, ColumnSelection]:
        """Return the selected test together with that test's column selection.

        Returns:
            ``(test, selection)``, used by the controller both to decide
            what to compute and to detect stale results.
        """
        test = self.selected_test()
        match test:
            case HypothesisTest.GROUP_COMPARISON:
                return test, self.group_comparison_selection()
            case HypothesisTest.CHI_SQUARE:
                return test, self.chi_square_selection()
