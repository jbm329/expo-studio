from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QWidget

from gui.dialogs.workflows.file.file_dialog_service import (
    DirectoryRequest,
    NullFileDialogService,
    OpenFileRequest,
    QtFileDialogService,
    SaveFileRequest,
)



@pytest.fixture
def qt_file_service():
    return QtFileDialogService()

@pytest.fixture
def null_file_service():
    return NullFileDialogService()


@pytest.fixture
def parent_widget(qt_app):
    return QWidget()


def test_null_file_service(null_file_service, parent_widget):
    # Test open file
    null_file_service.enqueue_open_response("test.txt", "Text files (*.txt)")
    path, filter = null_file_service.get_open_filename(
        parent_widget, 
        OpenFileRequest(title="Open", initial_path="", filter_str="All (*.*)")
    )
    assert path == "test.txt"
    assert filter == "Text files (*.txt)"

    # Test save file
    null_file_service.enqueue_save_response("save.txt")
    path, filter = null_file_service.get_save_filename(
        parent_widget, 
        SaveFileRequest(title="Save", initial_path="", filter_str="All (*.*)")
    )
    assert path == "save.txt"

    # Test directory
    null_file_service.enqueue_directory_response("/tmp")
    path = null_file_service.get_existing_directory(
        parent_widget, 
        DirectoryRequest(title="Dir", initial_path="")
    )
    assert path == "/tmp"


@patch("expo_jbm329.gui.dialogs.file_dialog_service.QFileDialog")
def test_qt_file_service_open(mock_fd_class, qt_file_service, parent_widget):
    mock_fd_class.getOpenFileName.return_value = ("selected.txt", "Filter")
    
    req = OpenFileRequest(title="Select File", initial_path="", filter_str="All (*.*)")
    path, filter = qt_file_service.get_open_filename(parent_widget, req)
    
    assert path == "selected.txt"
    assert filter == "Filter"
    mock_fd_class.getOpenFileName.assert_called_once_with(
        parent_widget, "Select File", "", "All (*.*)"
    )


@patch("expo_jbm329.gui.dialogs.file_dialog_service.QFileDialog")
def test_qt_file_service_save(mock_fd_class, qt_file_service, parent_widget):
    mock_fd_class.getSaveFileName.return_value = ("saved.txt", "Filter")
    
    req = SaveFileRequest(title="Save File", initial_path="default.txt", filter_str="All (*.*)")
    path, filter = qt_file_service.get_save_filename(parent_widget, req)
    
    assert path == "saved.txt"
    mock_fd_class.getSaveFileName.assert_called_once_with(
        parent_widget, "Save File", "default.txt", "All (*.*)"
    )

@patch("expo_jbm329.gui.dialogs.file_dialog_service.QFileDialog")
def test_qt_file_service_directory(mock_fd_class, qt_file_service, parent_widget):
    mock_fd_class.getExistingDirectory.return_value = "/some/dir"
    
    req = DirectoryRequest(title="Choose Dir", initial_path="")
    path = qt_file_service.get_existing_directory(parent_widget, req)
    
    assert path == "/some/dir"
    mock_fd_class.getExistingDirectory.assert_called_once_with(
        parent_widget, "Choose Dir", ""
    )
