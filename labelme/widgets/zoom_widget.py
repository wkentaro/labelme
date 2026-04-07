from __future__ import annotations

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets


class ZoomWidget(QtWidgets.QSpinBox):
    def __init__(self, value: int = 100) -> None:
        super().__init__()
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setRange(1, 1000)
        self.setValue(value)
        self.setSuffix(" %")
        self.setToolTip("Zoom Level")
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStatusTip(self.toolTip())

    def minimumSizeHint(self) -> QtCore.QSize:
        base_height = super().minimumSizeHint().height()
        font_metrics = QtGui.QFontMetrics(self.font())
        text_width = font_metrics.width(str(self.maximum()))
        return QtCore.QSize(text_width, base_height)
