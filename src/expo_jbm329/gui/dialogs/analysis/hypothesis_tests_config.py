"""Hypothesis Tests configuration widget (test selector + per-test column pickers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

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

    Column changes are pending until the user clicks Apply, which stores
    the configuration and emits `apply_requested`; `AnalysisController`
    then computes the applied test. Switching test emits `test_changed`
    so the content pane can stop showing the previous test's result.
    Apply is disabled for a test the dataset has no eligible columns for.
    """

    test_changed = pyqtSignal()
    apply_requested = pyqtSignal()

    def __init__(
        self,
        group_comparison: GroupComparisonResult,
        chi_square: ChiSquareResult,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            group_comparison: Default or most recently computed Group
                Comparison result, used to populate that test's column
                pickers.
            chi_square: Default or most recently computed chi-square
                result, used to populate that test's column pickers.
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
            self._stack.addWidget(self._group_comparison_config)
        else:
            self._stack.addWidget(self._build_unavailable_label())

        self._chi_square_config: ChiSquareConfigWidget | None = None
        if len(chi_square.available_columns) >= _COLUMNS_PER_CHI_SQUARE_TEST:
            self._chi_square_config = ChiSquareConfigWidget(chi_square, self._stack)
            self._stack.addWidget(self._chi_square_config)
        else:
            self._stack.addWidget(self._build_unavailable_label())

        self._apply_button = QPushButton(self.tr("Apply"), self)
        layout.addWidget(self._apply_button)
        layout.addStretch(1)

        self._applied_configuration: tuple[HypothesisTest, ColumnSelection] | None = None
        self._update_apply_button()

        # Connected only after the initial population above, so setting up
        # the default test never emits a spurious first signal.
        self._test_combo.currentIndexChanged.connect(self._on_test_changed)
        self._apply_button.clicked.connect(self._on_apply_clicked)

    def _build_unavailable_label(self) -> QLabel:
        """Build the page shown for a test the dataset has no eligible columns for."""
        label = QLabel(self.tr("This test is not available for the selected dataset."), self._stack)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    def _on_test_changed(self, index: int) -> None:
        """Show the selected test's page and announce the test change."""
        self._stack.setCurrentIndex(index)
        self._update_apply_button()
        self.test_changed.emit()

    def _on_apply_clicked(self) -> None:
        """Apply the pending test and column selection, and request its computation."""
        self._applied_configuration = self.current_configuration()
        self.apply_requested.emit()

    def _update_apply_button(self) -> None:
        """Enable Apply only when the selected test is available for the dataset."""
        self._apply_button.setEnabled(self.is_selected_test_available())

    def is_selected_test_available(self) -> bool:
        """Return whether the dataset has eligible columns for the selected test."""
        match self.selected_test():
            case HypothesisTest.GROUP_COMPARISON:
                return self._group_comparison_config is not None
            case HypothesisTest.CHI_SQUARE:
                return self._chi_square_config is not None

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

    def applied_configuration(self) -> tuple[HypothesisTest, ColumnSelection] | None:
        """Return the most recently applied ``(test, selection)``, or `None` before the first Apply."""
        return self._applied_configuration

    def current_configuration(self) -> tuple[HypothesisTest, ColumnSelection]:
        """Return the selected test together with that test's (possibly not yet applied) column selection.

        Returns:
            ``(test, selection)``, stored as the applied configuration when
            the user clicks Apply.
        """
        test = self.selected_test()
        match test:
            case HypothesisTest.GROUP_COMPARISON:
                return test, self.group_comparison_selection()
            case HypothesisTest.CHI_SQUARE:
                return test, self.chi_square_selection()
