from __future__ import annotations

from typing import Final

from PySide6 import QtCore
from PySide6 import QtWidgets

_ZOOM_LEVEL_LABEL: Final = "Zoom Level"


class ZoomWidget(QtWidgets.QDoubleSpinBox):
    PERCENT_MAX: int = 1000
    PERCENT_DECIMALS: int = 1
    PERCENT_SUFFIX: str = " %"

    def __init__(self) -> None:
        super().__init__()
        self.setDecimals(self.PERCENT_DECIMALS)
        self.setRange(1, self.PERCENT_MAX)
        self.setValue(100)
        self.setSuffix(self.PERCENT_SUFFIX)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setToolTip(_ZOOM_LEVEL_LABEL)
        self.setStatusTip(_ZOOM_LEVEL_LABEL)

        sample = f"{self.PERCENT_MAX:.{self.PERCENT_DECIMALS}f}{self.PERCENT_SUFFIX}"
        min_width = self.fontMetrics().horizontalAdvance(sample)
        self.setMinimumWidth(min_width)
