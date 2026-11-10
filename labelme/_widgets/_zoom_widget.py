from __future__ import annotations

import math
from typing import Final
from typing import override

from PySide6 import QtCore
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .._utils import modifier_text

# The usual zoom floor, in percent. MainWindow lowers it for images too big to
# fit at this zoom.
MIN_ZOOM: Final = 1.0

# One zoom step, in or out. Multiplicative, so a step changes the view by the
# same share at every zoom.
ZOOM_STEP_FACTOR: Final = 1.1


class ZoomWidget(QtWidgets.QDoubleSpinBox):
    """Zoom percent, kept exact and shown to three significant digits.

    Text that shows the current zoom means the current zoom, so showing 188.4
    as "188%" never rounds it.
    """

    def __init__(self) -> None:
        super().__init__()
        # Enough decimals that fit modes and 1% zooms don't snap.
        self.setDecimals(6)
        self.setRange(MIN_ZOOM, 1000)
        self.setSuffix("%")
        self.setValue(100)
        # Apply typed text on Enter, not on every keystroke.
        self.setKeyboardTracking(False)
        self.setAccessibleName(self.tr("Zoom"))
        self.setToolTip(
            self.tr("Hold %s and scroll to zoom the canvas")
            % modifier_text(modifiers=Qt.KeyboardModifier.ControlModifier)
        )

    @property
    def scale(self) -> float:
        return 0.01 * self.value()

    @override
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

    @override
    def valueFromText(self, text: str, /) -> float:
        value = super().valueFromText(text)
        # Stateless on purpose: tracking which text the user typed broke on
        # undo, revert and same-value refits.
        shown = super().valueFromText(self.textFromValue(self.value()))
        if value == shown:
            return self.value()
        return value

    @override
    def stepBy(self, steps: int, /) -> None:
        # Typed text not yet confirmed is the starting point.
        self.interpretText()
        self.setValue(self.value() * ZOOM_STEP_FACTOR**steps)

    def stepEnabled(self) -> QtWidgets.QAbstractSpinBox.StepEnabledFlag:
        if self.valueFromText(self.cleanText()) == self.value():
            return super().stepEnabled()
        # stepBy starts from the typed text, so allow it even at a range end.
        flag = QtWidgets.QAbstractSpinBox.StepEnabledFlag
        return flag.StepUpEnabled | flag.StepDownEnabled
