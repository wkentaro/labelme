from __future__ import annotations

from PySide6 import QtGui
from PySide6 import QtWidgets


class StatusStats(QtWidgets.QLabel):
    def __init__(self) -> None:
        super().__init__("")

        font = QtGui.QFont()
        font.setFamily("monospace")
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        self.setFont(font)
