from __future__ import annotations

from typing import Final

from PySide6 import QtCore
from PySide6 import QtWidgets


class ZoomWidget(QtWidgets.QDoubleSpinBox):
    PERCENT_MAX: Final[int] = 1000
    PERCENT_DECIMALS: Final[int] = 1
    PERCENT_SUFFIX: Final[str] = " %"

    def __init__(self) -> None:
        super().__init__()
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setDecimals(self.PERCENT_DECIMALS)
        self.setSuffix(self.PERCENT_SUFFIX)
        self.setRange(1, self.PERCENT_MAX)
        self.setValue(100)

        tip = self.tr("Zoom percentage")
        self.setAccessibleName(self.tr("Zoom"))
        self.setToolTip(tip)
        self.setStatusTip(tip)

        self.setMinimumWidth(
            self.fontMetrics().horizontalAdvance(
                f"{self.PERCENT_MAX:.{self.PERCENT_DECIMALS}f}{self.PERCENT_SUFFIX}"
            )
        )

    @property
    def scale(self) -> float:
        return self.value() / 100
