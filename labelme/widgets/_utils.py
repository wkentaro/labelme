from PyQt5 import QtGui
from PyQt5 import QtWidgets


def set_font_size(widget: QtWidgets.QWidget, point_size: int) -> None:
    font: QtGui.QFont = widget.font()
    font.setPointSize(point_size)
    widget.setFont(font)
