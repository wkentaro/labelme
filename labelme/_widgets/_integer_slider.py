from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets


class IntegerSlider(QtWidgets.QWidget):
    value_changed = QtCore.Signal(int)

    def __init__(
        self,
        *,
        minimum: int,
        maximum: int,
        value: int,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._slider.setRange(minimum, maximum)
        self._slider.setTracking(False)
        self._value_label = QtWidgets.QLabel()
        self._value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self._value_label.setMinimumWidth(
            self._value_label.fontMetrics().horizontalAdvance(str(maximum))
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._slider, stretch=1)
        layout.addWidget(self._value_label)

        self._slider.sliderMoved.connect(self._value_label.setNum)
        self._slider.valueChanged.connect(self._on_value_changed)
        self.set_value(value)

    def setAccessibleName(self, name: str, /) -> None:
        super().setAccessibleName(name)
        self._slider.setAccessibleName(name)

    @property
    def value(self) -> int:
        return self._slider.value()

    def set_value(self, value: int, /) -> None:
        self._slider.setValue(value)
        self._value_label.setNum(self._slider.value())

    def _on_value_changed(self, value: int, /) -> None:
        self._value_label.setNum(value)
        self.value_changed.emit(value)
