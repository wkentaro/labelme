from __future__ import annotations

import math

from PySide6 import QtCore
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .._utils import modifier_text


class ZoomWidget(QtWidgets.QDoubleSpinBox):
    """Zoom percent, kept exact and shown to three significant digits.

    The text is read back as a value only when the user edited it, so showing
    188.4 as "188%" never rounds the zoom.
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
        # The last text the user typed. Qt's own resets replace the text without
        # textEdited, so a mismatch means the edit is gone.
        self._edited_text: str | None = None
        self.lineEdit().textEdited.connect(self._remember_edited_text)
        # A new value, typed or set by a fit mode, ends the edit.
        self.valueChanged.connect(lambda: self._remember_edited_text(None))
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
        if self.lineEdit().text() != self._edited_text:
            return self.value()
        return super().valueFromText(text)

    def _remember_edited_text(self, text: str | None, /) -> None:
        self._edited_text = text

    def stepBy(self, steps: int, /) -> None:
        # Typed text not yet confirmed is the starting point. Multiplicative, so
        # a step changes the view by the same share at every zoom.
        self.interpretText()
        self.setValue(self.value() * 1.1**steps)

    def stepEnabled(self) -> QtWidgets.QAbstractSpinBox.StepEnabledFlag:
        if self.lineEdit().text() != self._edited_text:
            return super().stepEnabled()
        # stepBy starts from the typed text, so allow it even at a range end.
        flag = QtWidgets.QAbstractSpinBox.StepEnabledFlag
        return flag.StepUpEnabled | flag.StepDownEnabled
