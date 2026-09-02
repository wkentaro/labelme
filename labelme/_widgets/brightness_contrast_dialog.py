from __future__ import annotations

from collections.abc import Callable
from typing import Final

import PIL.Image
import PIL.ImageEnhance
import PIL.ImageStat
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

_NEUTRAL: Final = 50


class BrightnessContrastDialog(QtWidgets.QDialog):
    def __init__(
        self,
        *,
        img: PIL.Image.Image,
        callback: Callable[[QImage], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Brightness/Contrast"))
        self._publish = callback

        # Alpha rides along as an untouched band; every other mode collapses
        # to RGB so one lookup table covers all color channels.
        self._img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        self.slider_brightness = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.slider_contrast = QtWidgets.QSlider(Qt.Orientation.Horizontal)

        grid = QtWidgets.QGridLayout(self)
        grid.setColumnStretch(1, 1)
        captioned = (
            (self.tr("Brightness:"), self.slider_brightness),
            (self.tr("Contrast:"), self.slider_contrast),
        )
        for row, (caption, slider) in enumerate(captioned):
            slider.setRange(0, 3 * _NEUTRAL)
            slider.setValue(_NEUTRAL)
            readout = QtWidgets.QLabel(_as_percent(slider.value()))
            readout.setAlignment(Qt.AlignmentFlag.AlignRight)
            slider.valueChanged.connect(
                lambda value, readout=readout: readout.setText(_as_percent(value))
            )
            slider.valueChanged.connect(lambda _value: self.apply())
            grid.addWidget(QtWidgets.QLabel(caption), row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(readout, row, 2)

    def apply(self) -> None:
        gain = self.slider_brightness.value() / _NEUTRAL
        spread = self.slider_contrast.value() / _NEUTRAL
        identity = list(range(256))
        alpha_lut = identity if self._img.mode == "RGBA" else []
        ramp = PIL.Image.frombytes("L", (256, 1), bytes(identity))
        bright_ramp = PIL.ImageEnhance.Brightness(ramp).enhance(gain)
        bright_lut = list(bright_ramp.tobytes())
        bright_img = (
            self._img if gain == 1.0 else self._img.point(bright_lut * 3 + alpha_lut)
        )

        if spread == 1.0:
            img = bright_img
        else:
            # Pillow derives the contrast pivot after brightness has clipped
            # and rounded, so the combined table must use that intermediate.
            pivot = int(PIL.ImageStat.Stat(bright_img.convert("L")).mean[0] + 0.5)
            contrast_ramp = PIL.Image.blend(
                PIL.Image.new("L", ramp.size, pivot), bright_ramp, spread
            )
            contrast_lut = list(contrast_ramp.tobytes())
            img = self._img.point(contrast_lut * 3 + alpha_lut)

        image_format = (
            QImage.Format.Format_RGBA8888
            if img.mode == "RGBA"
            else QImage.Format.Format_RGB888
        )
        qimage = QImage(
            img.tobytes(),
            img.width,
            img.height,
            img.width * len(img.getbands()),
            image_format,
        )
        self._publish(qimage)


def _as_percent(value: int, /) -> str:
    return f"{value * 100 // _NEUTRAL}%"
