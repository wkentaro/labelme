from __future__ import annotations

import math

from PySide6 import QtCore
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .._utils import modifier_text


class ZoomWidget(QtWidgets.QDoubleSpinBox):
    """Zoom percent, kept exact and shown to three significant digits.

    Text that shows the current zoom means the current zoom, so showing 188.4
    as "188%" never rounds it.
    """

    def __init__(self) -> None:
        super().__init__()
        # Enough decimals that fit modes and 1% zooms don't snap.
        self.setDecimals(6)
        self.setRange(1, 1000)
        self.setSuffix("%")
        self.setValue(100)
        # Apply typed text on Enter, not on every keystroke.
        self.setKeyboardTracking(False)
        self.setAccessibleName(self.tr("Zoom"))
        self.setToolTip(
            self.tr("Hold %s and scroll to zoom the canvas")
            % modifier_text(Qt.KeyboardModifier.ControlModifier)
        )

    @property
    def scale(self) -> float:
        return 0.01 * self.value()

    def textFromValue(self, value: float, /) -> str:
        # Three significant digits: 1.23, 12.3, 188.
        # Qt formats 0 before the range is set.
        magnitude = math.floor(math.log10(value)) if value > 0 else 0
        decimals = max(0, 2 - magnitude)
        locale = self.locale()
        locale.setNumberOptions(QtCore.QLocale.NumberOption.OmitGroupSeparator)
        text = locale.toString(value, "f", decimals)
        decimal_point = locale.decimalPoint()
        if decimal_point in text:
            text = text.rstrip("0").removesuffix(decimal_point)
        return text

    def valueFromText(self, text: str, /) -> float:
        value = super().valueFromText(text)
        # Stateless on purpose: tracking which text the user typed broke on
        # undo, revert and same-value refits.
        shown = super().valueFromText(self.textFromValue(self.value()))
        if value == shown:
            return self.value()
        return value

    def stepBy(self, steps: int, /) -> None:
        # Typed text not yet confirmed is the starting point. Multiplicative, so
        # a step changes the view by the same share at every zoom.
        self.interpretText()
        self.setValue(self.value() * 1.1**steps)

    def stepEnabled(self) -> QtWidgets.QAbstractSpinBox.StepEnabledFlag:
        if self.valueFromText(self.cleanText()) == self.value():
            return super().stepEnabled()
        # stepBy starts from the typed text, so allow it even at a range end.
        flag = QtWidgets.QAbstractSpinBox.StepEnabledFlag
        return flag.StepUpEnabled | flag.StepDownEnabled
