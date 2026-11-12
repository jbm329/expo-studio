"""Current-join status identity in preview rendering."""

from __future__ import annotations

import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from expo_jbm329.gui.dialogs.workflows.join.join_preview_dialog import JoinPreviewDialog
from expo_jbm329.services.data_operations.joins import JoinMetadata
from expo_jbm329.utils.models import JoinPreviewModel


@pytest.mark.parametrize("ascending", [False, True])
def test_highlighting_uses_only_explicit_current_status_after_sorting(ascending: bool) -> None:
    """Historical status and NULL columns do not receive current-join colors."""
    status = "join_status (Film FULL OUTER Actor) 2"
    frame = pd.DataFrame({
        "id": [3, 1, 2],
        "join_status": pd.Series([pd.NA, "right_only", "left_only"], dtype="string"),
        status: pd.Categorical(["right_only", "left_only", "both"]),
    })
    original = frame.copy(deep=True)
    model = JoinPreviewModel(frame, status_column=status)
    model.sort(0, Qt.SortOrder.AscendingOrder if ascending else Qt.SortOrder.DescendingOrder)
    for row in range(3):
        assert model.data(model.index(row, 1), Qt.ItemDataRole.BackgroundRole) is None
        current = model.data(model.index(row, 2))
        color = model.data(model.index(row, 2), Qt.ItemDataRole.BackgroundRole)
        if current == "left_only":
            assert color == QColor("#fff3cd")
        elif current == "right_only":
            assert color == QColor("#f8d7da")
        else:
            assert color is None
    pd.testing.assert_frame_equal(frame, original)


def test_explicit_preview_status_is_not_replaced_or_fabricated() -> None:
    """Dialog routes the supplied identity without injecting legacy metadata."""
    status = "join_status (Film LEFT Actor)"
    frame = pd.DataFrame({"id": [1], status: ["left_only"]})
    original = frame.copy(deep=True)
    dialog = JoinPreviewDialog(
        None, df=frame, metadata=JoinMetadata(0.0, 1.0, 0.0, "one-to-one", 1), status_column=status
    )
    try:
        assert list(dialog.model.data_frame().columns) == ["id", status]
        assert dialog.model.data(dialog.model.index(0, 1), Qt.ItemDataRole.BackgroundRole) == QColor("#fff3cd")
        pd.testing.assert_frame_equal(frame, original)
    finally:
        dialog.close()


def test_explicit_missing_status_fails_instead_of_reporting_all_matched() -> None:
    """Explicit missing metadata is an error in the model and dialog."""
    frame = pd.DataFrame({"join_status": ["both"]})
    with pytest.raises(ValueError, match="must occur exactly once"):
        JoinPreviewModel(frame, status_column="missing")
    with pytest.raises(ValueError, match="is missing"):
        JoinPreviewDialog(
            None, df=frame, metadata=JoinMetadata(1.0, 0.0, 0.0, "one-to-one", 1), status_column="missing"
        )


def test_legacy_dialog_fallback_does_not_mutate_source() -> None:
    """Existing direct callers retain their established no-status behavior."""
    frame = pd.DataFrame({"id": [1]})
    dialog = JoinPreviewDialog(None, df=frame, metadata=JoinMetadata(1.0, 0.0, 0.0, "one-to-one", 1))
    try:
        assert list(frame.columns) == ["id"]
        assert dialog.model.data_frame()["join_status"].tolist() == ["both"]
    finally:
        dialog.close()
