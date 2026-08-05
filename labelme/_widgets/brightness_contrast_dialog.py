from __future__ import annotations

from collections.abc import Callable

import PIL.Image
import PIL.ImageEnhance
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


class BrightnessContrastDialog(QtWidgets.QDialog):
    _base_value = 50

    img: PIL.Image.Image

    def __init__(
        self,
        img: PIL.Image.Image,
        callback: Callable[[QImage], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Brightness/Contrast"))
        self.setModal(True)

        self._on_image_changed = callback

        grid = QtWidgets.QGridLayout()
        grid.setColumnStretch(1, 1)
        self.slider_brightness = self._add_slider_row(
            grid=grid, row=0, title=self.tr("Brightness:")
        )
        self.slider_contrast = self._add_slider_row(
            grid=grid, row=1, title=self.tr("Contrast:")
        )
        self.setLayout(grid)

        self._alpha = None
        if "A" in img.getbands():
            self._alpha = img.getchannel("A")
        if img.mode != "RGB":
            img = img.convert("RGB")
        self.img = img

    def _add_slider_row(
        self, grid: QtWidgets.QGridLayout, row: int, title: str
    ) -> QtWidgets.QSlider:
        slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 3 * self._base_value)
        slider.setValue(self._base_value)

        value_label = QtWidgets.QLabel(self._format_factor(slider.value()))
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        slider.valueChanged.connect(lambda _: self.apply())
        slider.valueChanged.connect(
            lambda value: value_label.setText(self._format_factor(value))
        )

        grid.addWidget(QtWidgets.QLabel(title), row, 0)
        grid.addWidget(slider, row, 1)
        grid.addWidget(value_label, row, 2)
        return slider

    def _format_factor(self, value: int) -> str:
        return f"{value / self._base_value:.2f}"

    def apply(self) -> None:
        img: PIL.Image.Image = self.img
        enhancers = [
            (
                self.slider_brightness.value() / self._base_value,
                PIL.ImageEnhance.Brightness,
            ),
            (
                self.slider_contrast.value() / self._base_value,
                PIL.ImageEnhance.Contrast,
            ),
        ]
        for factor, enhancer_cls in enhancers:
            if factor == 1.0:
                continue
            img = enhancer_cls(img).enhance(factor)

        fmt: QImage.Format
        if self._alpha is None:
            fmt = QImage.Format.Format_RGB888
        else:
            img = img.convert("RGBA")
            img.putalpha(self._alpha)
            fmt = QImage.Format.Format_RGBA8888

        qimage = QImage(
            img.tobytes(), img.width, img.height, img.width * len(img.getbands()), fmt
        )
        self._on_image_changed(qimage)
