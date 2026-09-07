from __future__ import annotations

from typing import Final

from PySide6 import QtCore
from PySide6 import QtWidgets


class ZoomWidget(QtWidgets.QDoubleSpinBox):
    PERCENT_MAX: Final[int] = 1000
    PERCENT_DECIMALS: Final[int] = 1
    PERCENT_SUFFIX: Final[str] = " %"

    def __init__(self) -> None:
        ZOOM_LEVEL_LABEL: Final = "Zoom Level"

        super().__init__()
        self.setDecimals(self.PERCENT_DECIMALS)
        self.setRange(1, self.PERCENT_MAX)
        self.setValue(100)
        self.setSuffix(self.PERCENT_SUFFIX)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setToolTip(ZOOM_LEVEL_LABEL)
        self.setStatusTip(ZOOM_LEVEL_LABEL)

        sample = f"{self.PERCENT_MAX:.{self.PERCENT_DECIMALS}f}{self.PERCENT_SUFFIX}"
        min_width = self.fontMetrics().horizontalAdvance(sample)
        self.setMinimumWidth(min_width)

    @property
    def scale(self) -> float:
        # The spin box shows a percentage; the canvas draws with a factor.
        return 0.01 * self.value()
