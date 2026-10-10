"""Hypothesis Tests configuration widget (test selector + per-test column pickers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.analysis.chi_square_config import ChiSquareConfigWidget
from expo_jbm329.gui.dialogs.analysis.group_comparison_config import GroupComparisonConfigWidget
from expo_jbm329.services.analysis.categories import HypothesisTest
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.chi_square import ChiSquareResult
    from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult
    from expo_jbm329.services.analysis.paired_comparison import PairedComparisonResult

# A test's ordered column selection, or None when unavailable/incomplete.
ColumnSelection = tuple[str, ...] | None

_COLUMNS_PER_CHI_SQUARE_TEST = 2
_MIN_PAIRED_OCCASIONS = 2


class PairedComparisonConfigWidget(QWidget):
    """Lets the user select repeated-measure columns in occasion order."""

    selection_changed = pyqtSignal()

    def __init__(self, result: PairedComparisonResult, parent: QWidget | None = None) -> None:
        """Initialize the paired-test column checklist.

        Args:
            result: Initializer result containing available numeric columns
                and default selected occasions.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        selected = set(result.columns)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        group = QGroupBox(self.tr("Measurement columns"), self)
        group_layout = QVBoxLayout(group)
        label = QLabel(
            self.tr("Select at least two numeric columns. They are used in the order shown; each row is one subject."),
            group,
        )
        label.setWordWrap(True)
        group_layout.addWidget(label)

        self._columns_list = QListWidget(group)
        self._columns_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for column in result.available_numeric_columns:
            item = QListWidgetItem(column, self._columns_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if column in selected else Qt.CheckState.Unchecked)
        group_layout.addWidget(self._columns_list)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._select_all_button = QPushButton(self.tr("Select all"), group)
        self._clear_button = QPushButton(self.tr("Clear"), group)
        actions.addWidget(self._select_all_button)
        actions.addWidget(self._clear_button)
        group_layout.addLayout(actions)

        self._selection_label = QLabel(group)
        self._selection_label.setWordWrap(True)
        group_layout.addWidget(self._selection_label)
        self._update_selection_label()

        self._group_layout = group_layout
        layout.addWidget(group)
        self._columns_list.itemChanged.connect(self._on_item_changed)
        self._select_all_button.clicked.connect(lambda: self._set_all_columns_checked(checked=True))
        self._clear_button.clicked.connect(lambda: self._set_all_columns_checked(checked=False))

    def _set_all_columns_checked(self, *, checked: bool) -> None:
        """Set every measurement column to the same pending check state, notifying once on change."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        changed = False
        self._columns_list.blockSignals(True)
        try:
            for index in range(self._columns_list.count()):
                item = self._columns_list.item(index)
                if item is not None and item.checkState() != state:
                    item.setCheckState(state)
                    changed = True
        finally:
            self._columns_list.blockSignals(False)
        if changed:
            self._update_selection_label()
            self.selection_changed.emit()

    def add_action_button(self, button: QPushButton) -> None:
        """Show `button` inside the measurement-columns frame, below the checklist.

        Args:
            button: The owning configuration's Apply button.
        """
        self._group_layout.addWidget(button)

    def remove_action_button(self, button: QPushButton) -> None:
        """Remove `button` from the measurement-columns frame.

        Args:
            button: A button previously passed to `add_action_button`.
        """
        self._group_layout.removeWidget(button)

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        """Notify the parent that the pending occasion selection changed."""
        self._update_selection_label()
        self.selection_changed.emit()

    def _checked_columns(self) -> tuple[str, ...]:
        """Return checked columns in dataset order."""
        return tuple(
            item.text()
            for index in range(self._columns_list.count())
            if (item := self._columns_list.item(index)) is not None and item.checkState() is Qt.CheckState.Checked
        )

    def _update_selection_label(self) -> None:
        """Show the selection count and which test the selection will run."""
        self._selection_label.setText(self._selection_text(len(self._checked_columns())))

    def _selection_text(self, count: int) -> str:
        """Return the translated selection count, with guidance for the resulting test."""
        if count == 0:
            return self.tr("None selected - select at least {minimum}.").format(minimum=fmt_int(_MIN_PAIRED_OCCASIONS))
        if count < _MIN_PAIRED_OCCASIONS:
            return self.tr("{count} selected - select at least {minimum}.").format(
                count=fmt_int(count), minimum=fmt_int(_MIN_PAIRED_OCCASIONS)
            )
        # Mirrors the service: two occasions run Wilcoxon, more run Friedman.
        if count == _MIN_PAIRED_OCCASIONS:
            return self.tr("{count} selected - Wilcoxon signed-rank test.").format(count=fmt_int(count))
        return self.tr("{count} selected - Friedman test.").format(count=fmt_int(count))

    def selected_columns(self) -> tuple[str, ...] | None:
        """Return checked columns in dataset order when at least two are selected."""
        selected = self._checked_columns()
        return selected if len(selected) >= _MIN_PAIRED_OCCASIONS else None


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
        paired_comparison: PairedComparisonResult,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the configuration widget.

        Args:
            group_comparison: Default or most recently computed Group
                Comparison result, used to populate that test's column
                pickers.
            chi_square: Default or most recently computed chi-square
                result, used to populate that test's column pickers.
            paired_comparison: Default paired-test metadata, used to
                populate its measurement occasion checklist.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._test_combo = QComboBox(self)
        self._test_combo.addItem(self.tr("Group comparison"), HypothesisTest.GROUP_COMPARISON.value)
        self._test_combo.addItem(self.tr("Chi-square independence"), HypothesisTest.CHI_SQUARE.value)
        self._test_combo.addItem(self.tr("Paired comparison"), HypothesisTest.PAIRED_COMPARISON.value)

        form = QFormLayout()
        form.addRow(QLabel(self.tr("Test"), self), self._test_combo)
        layout.addLayout(form)

        # The test pages take the free height so Apply stays anchored to the
        # bottom of the Configuration pane for every test.
        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

        self._group_comparison_config: GroupComparisonConfigWidget | None = None
        if group_comparison.available_numeric_columns and group_comparison.available_grouping_columns:
            self._group_comparison_config = GroupComparisonConfigWidget(group_comparison, self._stack)
            self._group_comparison_config.selection_changed.connect(self._update_apply_button)
            self._stack.addWidget(self._group_comparison_config)
        else:
            self._stack.addWidget(self._build_unavailable_label())

        self._chi_square_config: ChiSquareConfigWidget | None = None
        if len(chi_square.available_columns) >= _COLUMNS_PER_CHI_SQUARE_TEST:
            self._chi_square_config = ChiSquareConfigWidget(chi_square, self._stack)
            self._chi_square_config.selection_changed.connect(self._update_apply_button)
            self._stack.addWidget(self._chi_square_config)
        else:
            self._stack.addWidget(self._build_unavailable_label())

        self._paired_comparison_config: PairedComparisonConfigWidget | None = None
        if len(paired_comparison.available_numeric_columns) >= _MIN_PAIRED_OCCASIONS:
            self._paired_comparison_config = PairedComparisonConfigWidget(paired_comparison, self._stack)
            self._paired_comparison_config.selection_changed.connect(self._update_apply_button)
            self._stack.addWidget(self._paired_comparison_config)
        else:
            self._stack.addWidget(self._build_unavailable_label())

        self._apply_button = QPushButton(self.tr("Apply"), self)
        self._layout = layout
        layout.addWidget(self._apply_button)
        self._apply_button_in_paired_frame = False

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
        self._place_apply_button()
        self._update_apply_button()
        self.test_changed.emit()

    def _place_apply_button(self) -> None:
        """Put Apply inside the paired checklist frame, matching Correlation, else at the pane bottom."""
        paired = self._paired_comparison_config
        in_paired_frame = paired is not None and self.selected_test() is HypothesisTest.PAIRED_COMPARISON
        if paired is None or in_paired_frame == self._apply_button_in_paired_frame:
            return
        if in_paired_frame:
            self._layout.removeWidget(self._apply_button)
            paired.add_action_button(self._apply_button)
        else:
            paired.remove_action_button(self._apply_button)
            self._apply_button.setParent(self)
            self._layout.addWidget(self._apply_button)
        self._apply_button.show()
        self._apply_button_in_paired_frame = in_paired_frame

    def _on_apply_clicked(self) -> None:
        """Apply the pending test and column selection, and request its computation."""
        self._applied_configuration = self.current_configuration()
        self.apply_requested.emit()

    def _update_apply_button(self) -> None:
        """Enable Apply only when the selected test is available for the dataset."""
        self._apply_button.setEnabled(self.is_selected_test_available() and self.current_configuration()[1] is not None)

    def is_selected_test_available(self) -> bool:
        """Return whether the dataset has eligible columns for the selected test."""
        match self.selected_test():
            case HypothesisTest.GROUP_COMPARISON:
                return self._group_comparison_config is not None
            case HypothesisTest.CHI_SQUARE:
                return self._chi_square_config is not None
            case HypothesisTest.PAIRED_COMPARISON:
                return self._paired_comparison_config is not None

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

    def paired_comparison_selection(self) -> ColumnSelection:
        """Return the selected paired-measure columns, if at least two are checked."""
        if self._paired_comparison_config is None:
            return None
        return self._paired_comparison_config.selected_columns()

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
            case HypothesisTest.PAIRED_COMPARISON:
                return test, self.paired_comparison_selection()
