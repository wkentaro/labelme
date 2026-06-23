from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme._utils.qt import new_icon


class InfoButton(QtWidgets.QToolButton):
    def __init__(self, tooltip: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setIcon(new_icon("phosphor/info.svg"))
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
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.setToolTip(tooltip)

    def enterEvent(self, a0: QtGui.QEnterEvent) -> None:
        super().enterEvent(a0)
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), self.toolTip())
