from __future__ import annotations

import math
from typing import Final

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from .._utils import modifier_text

_MIN_PERCENT: Final = 1.0
_MAX_PERCENT: Final = 1000.0


class ZoomWidget(QtWidgets.QAbstractSpinBox):
    """Zoom percent as a float, shown to three significant digits.

    The value lives here rather than in the text, so formatting for display
    never rounds the zoom, and the text is parsed only when the user edits it.
    """

    valueChanged = QtCore.Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self._value = 100.0
        self._locale = QtCore.QLocale()
        self._locale.setNumberOptions(QtCore.QLocale.NumberOption.OmitGroupSeparator)
        self.editingFinished.connect(self._commit_text)
        self.lineEdit().setText(self._format(self._value))
        self.setAccessibleName(self.tr("Zoom"))
        self.setToolTip(
            self.tr("Hold %s and scroll to zoom the canvas")
            % modifier_text(Qt.KeyboardModifier.ControlModifier)
        )

    def value(self) -> float:
        return self._value

    def setValue(self, value: float, /) -> None:
        value = min(max(float(value), _MIN_PERCENT), _MAX_PERCENT)
        changed = value != self._value
        self._value = value
        text = self._format(value)
        # Fit modes set the value on every resize; leave unchanged text alone.
        if text != self.lineEdit().text():
            self.lineEdit().setText(text)
        if changed:
            self.valueChanged.emit(value)

    @property
    def scale(self) -> float:
        return 0.01 * self._value

    def stepBy(self, steps: int, /) -> None:
        # Multiplicative, so a step changes the view by the same share at
        # every zoom. Typed text not yet confirmed is the starting point.
        self._commit_text()
        self.setValue(self._value * 1.1**steps)

    def sizeHint(self) -> QtCore.QSize:
        # QAbstractSpinBox doesn't know the widest text, so size for it here.
        self.ensurePolished()
        width = max(
            self.fontMetrics().horizontalAdvance(self._format(value))
            for value in (8.88, 88.8, _MAX_PERCENT)
        )
        option = QtWidgets.QStyleOptionSpinBox()
        self.initStyleOption(option)
        # One digit of slack keeps the text off the frame, as QDoubleSpinBox did.
        width += self.fontMetrics().horizontalAdvance("0")
        content = QtCore.QSize(width, self.lineEdit().sizeHint().height())
        return self.style().sizeFromContents(
            QtWidgets.QStyle.ContentsType.CT_SpinBox, option, content, self
        )

    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    def stepEnabled(self) -> QtWidgets.QAbstractSpinBox.StepEnabledFlag:
        flags = QtWidgets.QAbstractSpinBox.StepEnabledFlag.StepNone
        if self._value < _MAX_PERCENT:
            flags |= QtWidgets.QAbstractSpinBox.StepEnabledFlag.StepUpEnabled
        if self._value > _MIN_PERCENT:
            flags |= QtWidgets.QAbstractSpinBox.StepEnabledFlag.StepDownEnabled
        return flags

    def validate(self, text: str, pos: int, /) -> object:
        if self._parse(text) is not None:
            return QtGui.QValidator.State.Acceptable, text, pos
        decimal_point = self._locale.decimalPoint()
        if all(c.isdigit() or c == decimal_point for c in _number(text)):
            return QtGui.QValidator.State.Intermediate, text, pos
        return QtGui.QValidator.State.Invalid, text, pos

    def _commit_text(self) -> None:
        text = self.lineEdit().text()
        # Unedited text would round the exact value, and invalid text restores it.
        parsed = None if text == self._format(self._value) else self._parse(text)
        self.setValue(self._value if parsed is None else parsed)

    def _format(self, value: float, /) -> str:
        # Three significant digits: 1.23%, 12.3%, 188%.
        decimals = max(0, 2 - math.floor(math.log10(value)))
        text = self._locale.toString(value, "f", decimals)
        decimal_point = self._locale.decimalPoint()
        if decimal_point in text:
            text = text.rstrip("0").removesuffix(decimal_point)
        return f"{text}%"

    def _parse(self, text: str, /) -> float | None:
        value, ok = self._locale.toDouble(_number(text))
        if not ok or not math.isfinite(value) or value <= 0:
            return None
        return value


def _number(text: str, /) -> str:
    return text.strip().removesuffix("%").strip()
