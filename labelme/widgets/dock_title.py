from PyQt5 import QtCore
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QFont
from qtpy.QtWidgets import QLabel


class DockTitle(QLabel):
    def __init__(self, text) -> None:
        super().__init__()
        self.setGeometry(QRect(0, 0, 80, 40))
        self.setFont(QFont('Arial', 10))
        self.setAlignment(Qt.AlignCenter)
        self.setText(text)
        self.setMargin(8)

    def enterEvent(self, a0: QtCore.QEvent) -> None:
        self.setToolTip(
            "Click & hold to drag Windows and Toolbar to a new Position"
        )
        return super().enterEvent(a0)
