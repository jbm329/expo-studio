from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QImage, QPainter
from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem

from expo_jbm329.gui.dialogs.workflows.reshape.dimension_delegate import DimensionDelegate
from tests.test_reshape_dialog import make_dialog


def test_only_column_name_is_bold_and_literal_text_is_preserved():
    name = "<Patient>  & Id"
    dialog = make_dialog((name,), (0,))
    delegate = dialog.dimensions.itemDelegate()
    assert isinstance(delegate, DimensionDelegate)
    index = dialog.dimensions.model().index(0, 0)
    option = QStyleOptionViewItem()
    option.font = dialog.font()
    document = delegate._document(option, index)
    assert document.toPlainText() == f"{name} [int64]"
    fragments = []
    iterator = document.begin().begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        fragments.append((fragment.text(), fragment.charFormat().fontWeight()))
        iterator += 1
    assert fragments == [(name, QFont.Weight.Bold), (" [int64]", QFont.Weight.Normal)]
    dialog.close()


def test_delegate_renders_checked_and_selected_items_and_sizes_bold_names():
    dialog = make_dialog(("WideColumnName" * 10,), (0,))
    item = dialog.dimensions.item(0)
    item.setCheckState(Qt.CheckState.Checked)
    delegate = dialog.dimensions.itemDelegate()
    assert isinstance(delegate, DimensionDelegate)
    index = dialog.dimensions.model().index(0, 0)
    option = QStyleOptionViewItem()
    option.initFrom(dialog.dimensions)
    option.rect = dialog.rect()
    option.widget = dialog.dimensions
    size = delegate.sizeHint(option, index)
    assert size.width() > 0
    assert size.height() > 0
    image = QImage(1280, 100, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    for selected in (False, True):
        if selected:
            option.state |= QStyle.StateFlag.State_Selected
        delegate.paint(painter, option, index)
    painter.end()
    assert item.checkState() == Qt.CheckState.Checked
    assert item.text().endswith("[int64]")
    dialog.close()
