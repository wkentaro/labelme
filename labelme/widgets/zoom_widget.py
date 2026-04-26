from __future__ import annotations

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets


class ZoomWidget(QtWidgets.QSpinBox):
    def __init__(self, value: int = 100) -> None:
        super().__init__()
        self.setRange(1, 1000)
        self.setSuffix(" %")
        self.setValue(value)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setToolTip("Zoom Level")
        self.setStatusTip(self.toolTip())

    def minimumSizeHint(self) -> QtCore.QSize:
        base = super().minimumSizeHint()
        font_metrics = QtGui.QFontMetrics(self.font())
        digits_width = font_metrics.horizontalAdvance(str(self.maximum()))
        return QtCore.QSize(digits_width, base.height())
