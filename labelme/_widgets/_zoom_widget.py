from __future__ import annotations

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .._utils import modifier_text


class ZoomWidget(QtWidgets.QDoubleSpinBox):
    def __init__(self) -> None:
        super().__init__()
        self.setDecimals(1)
        self.setRange(1, 1000)
        self.setSuffix(" %")
        self.setValue(100)
        self.setAccessibleName(self.tr("Zoom"))
        self.setToolTip(
            self.tr("Hold %s and scroll to zoom the canvas")
            % modifier_text(Qt.KeyboardModifier.ControlModifier)
        )

    @property
    def scale(self) -> float:
        return 0.01 * self.value()
