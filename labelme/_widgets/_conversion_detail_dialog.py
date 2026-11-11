from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtWidgets

from ._integer_slider import IntegerSlider


class ConversionDetailDialog(QtWidgets.QDialog):
    # Asks for the Polygon Detail a Conversion with more than one possible
    # result needs; the caller previews each value on the canvas.
    _slider: IntegerSlider

    def __init__(
        self,
        *,
        title: str,
        detail: int,
        on_detail_changed: Callable[[int], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(self.tr("Polygon detail")))
        # The preview follows the drag, as the canvas shows each result.
        self._slider = IntegerSlider(
            minimum=0, maximum=100, value=detail, tracking=True
        )
        self._slider.setAccessibleName(self.tr("Polygon detail"))
        self._slider.value_changed.connect(on_detail_changed)
        layout.addWidget(self._slider)
        endpoints = QtWidgets.QHBoxLayout()
        endpoints.addWidget(QtWidgets.QLabel(self.tr("Smoother")))
        endpoints.addStretch(1)
        endpoints.addWidget(QtWidgets.QLabel(self.tr("More detail")))
        layout.addLayout(endpoints)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        assert ok is not None
        ok.setText(self.tr("Convert"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(320)

    @property
    def detail(self) -> int:
        return self._slider.value
