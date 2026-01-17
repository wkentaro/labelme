from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

from labelme.utils.qt import newIcon


class InfoButton(QtWidgets.QToolButton):
    def __init__(self, tooltip: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent=parent)
        self.setIcon(newIcon("info.svg"))
        self.setIconSize(QtCore.QSize(16, 16))
        self.setStyleSheet(
            """
            QToolButton {
                border: none;
                border-radius: 8px;
                padding: 0px;
            }
            QToolButton:hover {
                background-color: rgba(0, 0, 0, 0.1);
            }
            """
        )
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setToolTip(tooltip)

    def enterEvent(self, a0: QtCore.QEvent) -> None:
        super().enterEvent(a0)
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), self.toolTip())
