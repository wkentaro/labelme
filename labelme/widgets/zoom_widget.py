from __future__ import annotations

from typing import Final

from PyQt5 import QtCore
from PyQt5 import QtWidgets


class ZoomWidget(QtWidgets.QSpinBox):
    PERCENT_MAX: Final = 1000
    PERCENT_SUFFIX: Final = " %"

    def __init__(self) -> None:
        super().__init__()
        self.setRange(1, self.PERCENT_MAX)
        self.setValue(100)
        self.setSuffix(self.PERCENT_SUFFIX)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        tooltip = "Zoom Level"
        self.setToolTip(tooltip)
        self.setStatusTip(tooltip)
        self._apply_minimum_width()

    def _apply_minimum_width(self) -> None:
        sample = f"{self.PERCENT_MAX}{self.PERCENT_SUFFIX}"
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance(sample))
