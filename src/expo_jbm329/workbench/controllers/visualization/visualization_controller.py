"""Controller for visualization dialog workflow."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)
from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.gui.dialogs.visualization.visualization_dialog import VisualizationDialog
from expo_jbm329.utils.i18n_utils import tr
from expo_jbm329.workbench.controllers.visualization.visualization_chart_builder import (
    VisualizationChartBuilder,
    VisualizationError,
)

if TYPE_CHECKING:
    import pandas as pd
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.utils.visualization_models import VisualizationConfig
    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import (
        ResultTabManager,
    )


class VisualizationController:
    """Controller responsible for dataset visualization workflow."""

    TR_GENERIC_PREVIEW_ERROR = QT_TR_NOOP("An error occurred while rendering the visualization.")
    TR_DATASET_EMPTY = QT_TR_NOOP("The selected dataset is empty.")
    TR_CATEGORY_COLUMN_MISSING = QT_TR_NOOP("Select a category column.")
    TR_CATEGORY_COLUMN_NOT_FOUND = QT_TR_NOOP("The selected category column no longer exists in the dataset.")
    TR_MEASURE_MISSING = QT_TR_NOOP("Select a measure.")
    TR_AGGREGATION_MISSING = QT_TR_NOOP("Select an aggregation.")
    TR_VALUE_COLUMN_MISSING = QT_TR_NOOP("Select a measure column.")
    TR_VALUE_COLUMN_NOT_FOUND = QT_TR_NOOP("The selected measure column no longer exists in the dataset.")
    TR_NON_NUMERIC_REQUIRES_COUNT = QT_TR_NOOP("Non-numeric measure columns can only use Count or Count distinct.")
    TR_NO_DATA_AFTER_AGGREGATION = QT_TR_NOOP("No data remains after aggregation.")
    TR_PIE_NO_DATA = QT_TR_NOOP("No data available for the pie chart.")
    TR_SCATTER_AXES_MISSING = QT_TR_NOOP("Select both X and Y axes for the scatter chart.")
    TR_SCATTER_X_NOT_FOUND = QT_TR_NOOP("The selected X column no longer exists in the dataset.")
    TR_SCATTER_Y_NOT_FOUND = QT_TR_NOOP("The selected Y column no longer exists in the dataset.")
    TR_SCATTER_NO_DATA = QT_TR_NOOP("No data available for the scatter chart.")
    TR_HISTOGRAM_REQUIRES_COLUMN_MEASURE = QT_TR_NOOP("Histogram requires a column-based measure.")
    TR_HISTOGRAM_VALUE_MISSING = QT_TR_NOOP("Select a measure column for the histogram.")
    TR_HISTOGRAM_VALUE_NOT_FOUND = QT_TR_NOOP("The selected measure column no longer exists in the dataset.")
    TR_HISTOGRAM_NO_NUMERIC = QT_TR_NOOP("No numeric data available for the histogram.")

    @staticmethod
    def _tr(text: str) -> str:
        """Translate a UI string for this controller."""
        return tr("VisualizationController", text)

    def __init__(
        self,
        *,
        results: ResultTabManager,
        chart_builder: VisualizationChartBuilder | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the visualization controller.

        Args:
            results: ResultTabManager instance.
            chart_builder: Optional chart builder service.
            logger: Optional logger instance.
        """
        self._results = results
        self._chart_builder = chart_builder or VisualizationChartBuilder()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

    def open_dialog(self, parent: QWidget) -> None:
        """Open the visualization dialog.

        Args:
            parent: Parent widget for the dialog.
        """
        datasets = self._results.list_ready_datasets()
        if not datasets:
            return

        dialog = VisualizationDialog(
            parent=parent,
            datasets=datasets,
            active_tab_id=self._results.active_tab_id(),
        )

        dialog.dataset_changed.connect(lambda tab_id: self._on_dataset_changed(dialog, tab_id))
        dialog.preview_requested.connect(lambda config: self._on_preview_requested(dialog, config))

        initial_tab_id = dialog.selected_dataset_tab_id()
        if initial_tab_id:
            self._on_dataset_changed(dialog, initial_tab_id)

        dialog.exec()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_dataset_changed(self, dialog: VisualizationDialog, tab_id: str) -> None:
        """Handle dataset selection changes.

        Args:
            dialog: Active visualization dialog.
            tab_id: Selected dataset tab ID.
        """
        try:
            df = self._results.get_df_by_tab_id(tab_id)
            all_columns = [str(col) for col in df.columns]
            numeric_columns = self._numeric_columns(df)

            dialog.set_available_columns(
                all_columns=all_columns,
                numeric_columns=numeric_columns,
            )

            dialog.apply_smart_defaults(
                preferred_dimension=self._preferred_dimension_column(df),
                preferred_numeric_measure=self._preferred_numeric_measure_column(df),
            )

            dialog.show_empty_preview()

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
            self._logger.exception(
                "VisualizationController: failed to update visualization dialog columns for dataset '%s'.",
                tab_id,
            )
            dialog.show_error_preview(self._tr(self.TR_GENERIC_PREVIEW_ERROR))

    def _on_preview_requested(
        self,
        dialog: VisualizationDialog,
        config: VisualizationConfig,
    ) -> None:
        """Handle chart preview requests.

        Args:
            dialog: Active visualization dialog.
            config: Visualization configuration.
        """
        try:
            df = self._results.get_df_by_tab_id(config.dataset_tab_id)

            preview = dialog.preview_widget()
            figure = preview.figure
            figure.clear()

            ax = figure.add_subplot(111)
            self._chart_builder.draw(ax, df, config)

            preview.show_chart()

        except VisualizationError as e:
            self._logger.warning(
                "VisualizationController: visualization validation failed (code=%s, detail=%s).",
                e.code,
                e.detail,
                exc_info=True,
            )
            dialog.show_error_preview(self._map_error_code_to_ui_message(e.code))

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
            self._logger.exception("VisualizationController: unexpected visualization rendering failure.")
            dialog.show_error_preview(self._tr(self.TR_GENERIC_PREVIEW_ERROR))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _numeric_columns(self, df: pd.DataFrame) -> list[str]:
        """Return numeric column names from the DataFrame."""
        numeric: list[str] = []

        for col in df.columns:
            try:
                if is_numeric_dtype(df[col]) and not is_bool_dtype(df[col]):
                    numeric.append(str(col))
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
                continue

        return numeric

    def _preferred_dimension_column(self, df: pd.DataFrame) -> str | None:
        """Return the preferred default dimension column."""
        for col in df.columns:
            try:
                series = df[col]
                if is_datetime64_any_dtype(series):
                    return str(col)
                if not is_numeric_dtype(series):
                    return str(col)
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
                continue
        return None

    def _preferred_numeric_measure_column(self, df: pd.DataFrame) -> str | None:
        """Return the preferred default numeric measure column."""
        for col in df.columns:
            try:
                series = df[col]
                if is_numeric_dtype(series) and not is_bool_dtype(series):
                    return str(col)
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
                continue
        return None

    def _map_error_code_to_ui_message(self, code: str) -> str:
        """Map an internal visualization error code to a localized UI message."""
        error_map = {
            "dataset_empty": self._tr(self.TR_DATASET_EMPTY),
            "category_column_missing": self._tr(self.TR_CATEGORY_COLUMN_MISSING),
            "category_column_not_found": self._tr(self.TR_CATEGORY_COLUMN_NOT_FOUND),
            "measure_missing": self._tr(self.TR_MEASURE_MISSING),
            "aggregation_missing": self._tr(self.TR_AGGREGATION_MISSING),
            "value_column_missing": self._tr(self.TR_VALUE_COLUMN_MISSING),
            "value_column_not_found": self._tr(self.TR_VALUE_COLUMN_NOT_FOUND),
            "non_numeric_measure_requires_count": self._tr(self.TR_NON_NUMERIC_REQUIRES_COUNT),
            "no_data_after_aggregation": self._tr(self.TR_NO_DATA_AFTER_AGGREGATION),
            "pie_no_data": self._tr(self.TR_PIE_NO_DATA),
            "scatter_axes_missing": self._tr(self.TR_SCATTER_AXES_MISSING),
            "scatter_x_column_not_found": self._tr(self.TR_SCATTER_X_NOT_FOUND),
            "scatter_y_column_not_found": self._tr(self.TR_SCATTER_Y_NOT_FOUND),
            "scatter_no_data": self._tr(self.TR_SCATTER_NO_DATA),
            "histogram_requires_column_measure": self._tr(self.TR_HISTOGRAM_REQUIRES_COLUMN_MEASURE),
            "histogram_value_column_missing": self._tr(self.TR_HISTOGRAM_VALUE_MISSING),
            "histogram_value_column_not_found": self._tr(self.TR_HISTOGRAM_VALUE_NOT_FOUND),
            "histogram_no_numeric_data": self._tr(self.TR_HISTOGRAM_NO_NUMERIC),
        }
        return error_map.get(code, self._tr(self.TR_GENERIC_PREVIEW_ERROR))
