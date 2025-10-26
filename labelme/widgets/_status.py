from PyQt5 import QtGui
from PyQt5 import QtWidgets


class StatusStats(QtWidgets.QLabel):
    def __init__(self):
        super().__init__("")

        font = QtGui.QFont()
        font.setFamily("monospace")
        font.setStyleHint(QtGui.QFont.Monospace)
        self.setFont(font)
