from __future__ import annotations

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .._utils import modifier_text


class ZoomWidget(QtWidgets.QDoubleSpinBox):
    def __init__(self) -> None:
        super().__init__()
        self.setDecimals(1)
        self.setRange(1, 1000)
        self.setSuffix("%")
        self.setValue(100)
        self._edited_text: str | None = None
        self.lineEdit().textEdited.connect(self._remember_edited_text)
        self.setAccessibleName(self.tr("Zoom"))
        self.setToolTip(
            self.tr("Hold %s and scroll to zoom the canvas")
            % modifier_text(Qt.KeyboardModifier.ControlModifier)
        )

    def textFromValue(self, value: float, /) -> str:
        # Fit modes produce fractional zooms; show whole percent, keep the value.
        return f"{value:.0f}"

    def _remember_edited_text(self, text: str, /) -> None:
        self._edited_text = text

    def valueFromText(self, text: str, /) -> float:
        # Enter on the unedited box must not snap the value to the shown text.
        # Comparing text, not a flag, keeps a reverted invalid edit from
        # counting: Qt never displays the invalid text it reverted.
        edited, self._edited_text = text == self._edited_text, None
        if not edited:
            return self.value()
        return super().valueFromText(text)

    @property
    def scale(self) -> float:
        return 0.01 * self.value()
