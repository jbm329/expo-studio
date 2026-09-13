from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtWidgets import QTableView, QHeaderView
from PyQt6.QtGui import QMouseEvent
from expo_jbm329.utils.custom_header import ExpoHeaderView
from expo_jbm329.utils.models import MinimalModel
import pandas as pd
import pytest

def test_expo_header_view_init(qt_app):
    view = QTableView()
    header = ExpoHeaderView(Qt.Orientation.Horizontal, parent=view, view=view)
    assert header.orientation() == Qt.Orientation.Horizontal
    assert header._view == view

def test_expo_header_view_mouse_press_normal(qt_app):
    # Test normal click (should trigger standard behavior like sorting)
    view = QTableView()
    model = MinimalModel(pd.DataFrame({"A": [1, 2], "B": [3, 4]}))
    view.setModel(model)
    header = ExpoHeaderView(Qt.Orientation.Horizontal, parent=view, view=view)
    view.setHorizontalHeader(header)
    
    # Simulate a normal left click on the first column header (index 0)
    # We can't easily check if sorting was triggered without more setup,
    # but we can check if it calls super().mousePressEvent.
    # For now, just ensure it doesn't crash.
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    header.mousePressEvent(event)

def test_expo_header_view_ctrl_click(qt_app):
    view = QTableView()
    # Need a model so we have columns
    df = pd.DataFrame({"#": [1, 2], "A": [10, 20], "B": [30, 40]})
    model = MinimalModel(df)
    view.setModel(model)
    
    header = ExpoHeaderView(Qt.Orientation.Horizontal, parent=view, view=view)
    view.setHorizontalHeader(header)
    
    # Logical index 1 is column "A"
    # We need to make sure logicalIndexAt(pos) returns 1.
    # Since we don't have a real visible window, we might need to mock logicalIndexAt
    # or just rely on the fact that it's a unit test.
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(header, "logicalIndexAt", lambda pos: 1)
        
        # Simulate Ctrl+LeftClick
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(50, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier
        )
        
        header.mousePressEvent(event)
        
        # Verify column 1 is selected
        sel_model = view.selectionModel()
        assert any(ix.column() == 1 for ix in sel_model.selectedIndexes())
        
        # Toggle off
        header.mousePressEvent(event)
        assert not any(ix.column() == 1 for ix in sel_model.selectedIndexes())

def test_expo_header_view_ctrl_click_index_column(qt_app):
    view = QTableView()
    df = pd.DataFrame({"#": [1, 2], "A": [10, 20]})
    model = MinimalModel(df)
    view.setModel(model)
    header = ExpoHeaderView(Qt.Orientation.Horizontal, parent=view, view=view)
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(header, "logicalIndexAt", lambda pos: 0) # Index column
        
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(5, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier
        )
        
        header.mousePressEvent(event)
        
        # Column 0 should NOT be selected because of the check in _toggle_column_selection
        sel_model = view.selectionModel()
        assert not any(ix.column() == 0 for ix in sel_model.selectedIndexes())
