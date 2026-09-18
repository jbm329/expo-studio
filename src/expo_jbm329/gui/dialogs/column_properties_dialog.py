"""Dialog showing properties and statistics for a single column."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.data_operations.dtypes import SemanticDType
from expo_jbm329.services.data_profile.presentation import format_value_for_display
from expo_jbm329.services.data_profile.stat_defs import (
    STAT_DEFS,
    StatFormat,
)
from expo_jbm329.utils.format_utils import fmt_bytes, fmt_int, fmt_num, fmt_pct

if TYPE_CHECKING:
    from expo_jbm329.services.data_profile.column_data_profile import ColumnProfile
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    _HAS_MPL = True
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
    _HAS_MPL = False


class ColumnPropertiesDialog(QDialog):
    """Dialog showing properties and statistics for a single column."""

    def __init__(self, parent: QWidget, profile: ColumnProfile, semantics: SeriesSemantics | None):
        """Initialize the dialog.

        Args:
            parent: Parent widget.
            profile: Column profile to display.
            semantics: Series semantics for the column.
        """
        super().__init__(parent)
        self._profile = profile
        self._semantics = semantics
        self._layout = QVBoxLayout(self)

        self._build()

    # ------------------------------------------------------------------
    # Build orchestration
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.setWindowTitle(self.tr("Properties - {name}").format(name=self._profile.name))

        self._build_header()
        self._build_stats_table()
        self._build_plot()
        self._build_buttons()

        self.resize(720, 600)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> None:

        sem = self._profile.semantic_dtype
        storage = self._profile.storage_dtype

        semantic_label = str(sem.value)
        storage_label = storage

        is_object = storage == "object"
        is_string = storage.startswith("string")  # pandas string dtype

        is_text_storage = is_object or is_string

        is_mismatch = self._semantics is not None and sem.value in ("int", "float", "datetime") and is_text_storage

        if is_mismatch:
            text = self.tr("Type: <b>{sem}</b> ⚠ <span style='color:#666;'>({storage})</span>").format(
                sem=semantic_label, storage=storage_label
            )
        else:
            text = self.tr("Type: <b>{sem}</b> <span style='color:#666;'>({storage})</span>").format(
                sem=semantic_label, storage=storage_label
            )

        dtype_label = QLabel(text)
        dtype_label.setStyleSheet("font-size: 14px; margin-bottom: 4px;")
        self._layout.addWidget(dtype_label)

        if is_mismatch:
            if sem == SemanticDType.DATETIME:
                warn_text = self.tr("⚠ Column appears to contain dates but is stored as text.")
            elif sem in (SemanticDType.INT, SemanticDType.FLOAT):
                warn_text = self.tr("⚠ Column appears numeric but is stored as text.")
            else:
                warn_text = self.tr("⚠ Column is stored as text but may require conversion.")
            warn = QLabel(warn_text)
            warn.setStyleSheet("color: #cc6600; margin-bottom: 4px;")
            self._layout.addWidget(warn)

        if self._profile.stats.get("note.bytes"):
            warn = QLabel(self.tr("⚠ Column contains binary data and cannot be profiled."))
            warn.setStyleSheet("color: #cc0000; margin-bottom: 4px;")
            self._layout.addWidget(warn)

        stats = self._profile.stats

        n = int(stats.get("count.n", 0))
        missing = int(stats.get("missing.n", 0))
        missing_pct = float(stats.get("missing.pct", 0.0))
        unique = int(stats.get("unique.n", 0))
        unique_pct = float(stats.get("unique.pct", 0.0))

        summary = QLabel(
            f"{self.tr('Rows')}: <b>{fmt_int(n)}</b> &nbsp;&nbsp; "
            f"{self.tr('Missing')}: <b>{fmt_int(missing)}</b> ({fmt_pct(missing_pct)}) &nbsp;&nbsp; "
            f"{self.tr('Unique')}: <b>{fmt_int(unique)}</b> ({fmt_pct(unique_pct)})"
        )
        summary.setStyleSheet("margin-bottom: 6px;")
        self._layout.addWidget(summary)

        examples = stats.get("sample.values")

        if isinstance(examples, list) and examples:
            formatted = [format_value_for_display(v, self._semantics) for v in examples]
            ex_label = QLabel(f"{self.tr('Sample values')}: <i>{', '.join(formatted)}</i>")
            ex_label.setStyleSheet("margin-bottom: 8px;")

            self._layout.addWidget(ex_label)

        self._layout.addWidget(QLabel("<hr>"))

    # ------------------------------------------------------------------
    # Statistics table
    # ------------------------------------------------------------------

    def _build_stats_table(self) -> None:
        rows = self._format_stats_for_display(self._profile.stats)

        table = QTableWidget(self)
        table.setColumnCount(2)
        table.setRowCount(len(rows))

        hheader = table.horizontalHeader()
        if hheader is not None:
            hheader.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            hheader.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hheader.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        table.setHorizontalHeaderLabels([
            self.tr("Property"),
            self.tr("Value"),
        ])

        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        for r, (label, value) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(label))
            table.setItem(r, 1, QTableWidgetItem(value))

        table.resizeColumnsToContents()
        self._layout.addWidget(table)

    def _format_stats_for_display(self, stats: dict[str, Any]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []

        for key, value in stats.items():
            stat = STAT_DEFS.get(key)
            if stat is None:
                continue

            if key == "sample.values":
                continue

            label = self._tr_stat_label(key)

            if stat.fmt == StatFormat.INT:
                text = fmt_int(value)

            elif stat.fmt == StatFormat.FLOAT:
                text = fmt_num(value, sig=2)

            elif stat.fmt == StatFormat.PERCENT:
                text = fmt_pct(value)

            elif stat.fmt == StatFormat.BYTES:
                text = fmt_bytes(value)

            elif stat.fmt == StatFormat.VALUE:
                text = format_value_for_display(value, self._semantics)

            elif stat.fmt == StatFormat.LIST:
                if isinstance(value, list):
                    if value and isinstance(value[0], tuple):
                        parts = []
                        for item in value:
                            if len(item) == 3:
                                parts.append(f"{item[0]} ({fmt_int(item[1])}, {fmt_pct(item[2])})")
                            elif len(item) == 2:
                                parts.append(f"{item[0]} ({fmt_int(item[1])})")
                        text = "; ".join(parts)
                    else:
                        text = ", ".join(map(str, value[:5])) + (" …" if len(value) > 5 else "")
                else:
                    text = ""
            else:
                text = str(value)

            out.append((label, text))

        return out

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------

    def _build_plot(self) -> None:
        if not _HAS_MPL:
            lbl = QLabel(self.tr("Plot not available (matplotlib missing)."))
            lbl.setStyleSheet("color: #666;")
            self._layout.addWidget(lbl)
            return

        plot = self._profile.plot
        if not plot or not plot.kind:
            return

        fig = Figure(figsize=(5, 2.6), tight_layout=True)
        ax = fig.add_subplot(111)

        if plot.kind == "hist" and plot.bins and plot.counts:
            import numpy as np

            ax.bar(plot.bins[:-1], plot.counts, width=np.diff(plot.bins), align="edge", edgecolor="#333")
            ax.set_title(self.tr("Histogram"))

        elif plot.kind == "bar_topn" and plot.labels and plot.counts:
            ax.bar(range(len(plot.labels)), plot.counts)
            ax.set_xticks(range(len(plot.labels)))
            ax.set_xticklabels(
                [str(x)[:18] + ("…" if len(str(x)) > 18 else "") for x in plot.labels],
                rotation=30,
                ha="right",
            )
            ax.set_title(self.tr("Top values"))

        elif plot.kind == "bar_weekday" and plot.labels and plot.counts:
            ax.bar(range(len(plot.labels)), plot.counts)
            ax.set_xticks(range(len(plot.labels)))

            ax.set_xticklabels([self._tr_plot_label(k) for k in plot.labels])

            ax.set_title(self.tr("Weekday distribution"))

        elif plot.kind == "bar_bool" and plot.labels and plot.counts:
            ax.bar(range(len(plot.labels)), plot.counts)
            ax.set_xticks(range(len(plot.labels)))

            ax.set_xticklabels([self._tr_plot_label(k) for k in plot.labels])

            ax.set_title(self.tr("Distribution"))

        ax.grid(True, axis="y", alpha=0.25)
        self._layout.addWidget(FigureCanvas(fig))

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def _build_buttons(self) -> None:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        btn_copy = QPushButton(self.tr("Copy as Markdown"))
        buttons.addButton(btn_copy, QDialogButtonBox.ButtonRole.ActionRole)

        def to_markdown(data_rows: list[tuple[str, str]]) -> str:
            lines = ["| Property | Value |", "|---|---|"]
            for k, v in data_rows:
                lines.append(f"| {k} | {v} |")
            return "\n".join(lines)

        rows = self._format_stats_for_display(self._profile.stats)

        def copy():
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(to_markdown(rows))

        btn_copy.clicked.connect(copy)
        buttons.rejected.connect(self.reject)

        self._layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Translate labels
    # ------------------------------------------------------------------

    def _tr_stat_label(self, key: str) -> str:
        """Translate stat keys to UI labels."""
        return {
            "count.n": self.tr("Count (n)"),
            "missing.n": self.tr("Missing (n)"),
            "missing.pct": self.tr("Missing (%)"),
            "unique.n": self.tr("Unique (n)"),
            "unique.pct": self.tr("Unique (%)"),
            "memory.bytes": self.tr("Memory (bytes)"),
            "constant.flag": self.tr("Constant"),
            # Numeric
            "num.min": self.tr("Min"),
            "num.q1": self.tr("Q1"),
            "num.median": self.tr("Median"),
            "num.q3": self.tr("Q3"),
            "num.max": self.tr("Max"),
            "num.mean": self.tr("Mean"),
            "num.std": self.tr("Std deviation"),
            "num.mad": self.tr("MAD (median absolute deviation)"),
            "num.skew": self.tr("Skewness"),
            "num.kurtosis": self.tr("Kurtosis"),
            "num.zeros.n": self.tr("Zeros (n)"),
            "num.zeros.pct": self.tr("Zeros (%)"),
            "num.neg.n": self.tr("Negatives (n)"),
            "num.neg.pct": self.tr("Negatives (%)"),
            "num.pos.n": self.tr("Positives (n)"),
            "num.pos.pct": self.tr("Positives (%)"),
            # Boolean
            "bool.true.n": self.tr("True (n)"),
            "bool.true.pct": self.tr("True (%)"),
            "bool.false.n": self.tr("False (n)"),
            "bool.false.pct": self.tr("False (%)"),
            # Text / category
            "text.topn": self.tr("Top 3"),
            "text.len.min": self.tr("Length min"),
            "text.len.median": self.tr("Length median"),
            "text.len.max": self.tr("Length max"),
            "text.len.mean": self.tr("Length mean"),
            "text.empty.n": self.tr("Empty strings (n)"),
            # Datetime
            "dt.min": self.tr("Min datetime"),
            "dt.max": self.tr("Max datetime"),
            "dt.span.seconds": self.tr("Span (seconds)"),
            # Category
            "cat.count": self.tr("Categories (n)"),
            "cat.ordered": self.tr("Categories ordered"),
            # Notes
            "note.bytes": self.tr("Column contains binary data (bytes) and cannot be profiled."),
            # Samples
            "sample.values": self.tr("Sample values"),
        }.get(key, key)

    def _tr_plot_label(self, key: str) -> str:
        """Translate plot keys to UI labels."""
        return {
            "weekday.mon": self.tr("Mon"),
            "weekday.tue": self.tr("Tue"),
            "weekday.wed": self.tr("Wed"),
            "weekday.thu": self.tr("Thu"),
            "weekday.fri": self.tr("Fri"),
            "weekday.sat": self.tr("Sat"),
            "weekday.sun": self.tr("Sun"),
            "bool.true": self.tr("True"),
            "bool.false": self.tr("False"),
        }.get(key, key)
