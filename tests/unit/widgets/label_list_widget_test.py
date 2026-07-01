from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from pytestqt.qtbot import QtBot

from labelme._widgets.label_list_widget import HTMLDelegate


def _has_ink_from(image: QtGui.QImage, start_x: int) -> bool:
    for x in range(start_x, image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y) != QtGui.QColor(Qt.GlobalColor.white):
                return True
    return False


def test_html_delegate_does_not_clip_label_when_text_subrect_collapses(
    qtbot: QtBot,
) -> None:
    model = QtGui.QStandardItemModel()
    model.appendRow(QtGui.QStandardItem("LabelText " * 8))
    index = model.index(0, 0)

    delegate = HTMLDelegate()

    image = QtGui.QImage(400, 24, QtGui.QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QtGui.QPainter(image)

    option = QtWidgets.QStyleOptionViewItem()
    # A narrow item rect emulates the styles (e.g. Adwaita) whose text sub-rect
    # collapses because the delegate empties opt.text before measuring it.
    option.rect = QtCore.QRect(0, 0, 6, 24)
    option.palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QtGui.QColor("black")
    )
    delegate.paint(painter, option, index)
    painter.end()

    # The collapsed sub-rect is only 6px wide; ink well past it (x >= 20) proves
    # the widened clip rect let the label render instead of clipping it away.
    assert _has_ink_from(image, start_x=20)
