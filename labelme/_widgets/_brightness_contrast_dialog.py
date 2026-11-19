from __future__ import annotations

from collections.abc import Callable
from typing import Final

import PIL.Image
import PIL.ImageEnhance
import PIL.ImageStat
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

_NEUTRAL: Final = 100


class BrightnessContrastDialog(QtWidgets.QDialog):
    _publish: Callable[[QImage], None]
    _img: PIL.Image.Image

    slider_brightness: QtWidgets.QSlider
    slider_contrast: QtWidgets.QSlider

    def __init__(
        self,
        *,
        img: PIL.Image.Image,
        callback: Callable[[QImage], None],
        brightness: int | None = None,
        contrast: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Brightness/Contrast"))
        self._publish = callback

        self._img = _to_adjustable(img=img)
        self.slider_brightness = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.slider_contrast = QtWidgets.QSlider(Qt.Orientation.Horizontal)

        grid = QtWidgets.QGridLayout(self)
        grid.setColumnStretch(1, 1)
        captioned = (
            (self.tr("Brightness:"), self.slider_brightness, brightness),
            (self.tr("Contrast:"), self.slider_contrast, contrast),
        )
        for row, (caption, slider, value) in enumerate(captioned):
            slider.setRange(0, 3 * _NEUTRAL)
            slider.setSingleStep(2)
            slider.setPageStep(20)
            # Set before the signals connect: each change adjusts the whole
            # image, and the caller applies the starting values once.
            slider.setValue(_NEUTRAL if value is None else value)
            readout = QtWidgets.QLabel(_as_percent(value=slider.value()))
            readout.setAlignment(Qt.AlignmentFlag.AlignRight)
            slider.valueChanged.connect(
                lambda value, readout=readout: readout.setText(_as_percent(value=value))
            )
            slider.valueChanged.connect(lambda _value: self.apply())
            label = QtWidgets.QLabel(caption)
            label.setBuddy(slider)
            grid.addWidget(label, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(readout, row, 2)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults
            | QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        restore = buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults
        )
        assert restore is not None
        restore.clicked.connect(self._restore_defaults)
        buttons.rejected.connect(self.close)
        grid.addWidget(buttons, len(captioned), 0, 1, 3)
        self.setMinimumWidth(360)

    def _restore_defaults(self) -> None:
        self.slider_brightness.setValue(_NEUTRAL)
        self.slider_contrast.setValue(_NEUTRAL)

    def apply(self) -> None:
        self._publish(
            _adjust(
                img=self._img,
                brightness=self.slider_brightness.value(),
                contrast=self.slider_contrast.value(),
            )
        )


def adjust_brightness_contrast(
    *, img: PIL.Image.Image, brightness: int | None, contrast: int | None
) -> QImage:
    img = _to_adjustable(img=img)
    return _adjust(
        img=img,
        brightness=_NEUTRAL if brightness is None else brightness,
        contrast=_NEUTRAL if contrast is None else contrast,
    )


def _to_adjustable(*, img: PIL.Image.Image) -> PIL.Image.Image:
    # Alpha rides along as an untouched band; every other mode collapses
    # to RGB so one lookup table covers all color channels.
    return img.convert("RGBA" if "A" in img.getbands() else "RGB")


def _adjust(*, img: PIL.Image.Image, brightness: int, contrast: int) -> QImage:
    gain = brightness / _NEUTRAL
    spread = contrast / _NEUTRAL
    identity = list(range(256))
    alpha_lut = identity if img.mode == "RGBA" else []
    ramp = PIL.Image.frombytes("L", (256, 1), bytes(identity))
    bright_ramp = PIL.ImageEnhance.Brightness(ramp).enhance(gain)
    bright_lut = list(bright_ramp.tobytes())
    bright_img = img if gain == 1.0 else img.point(bright_lut * 3 + alpha_lut)

    if spread == 1.0:
        adjusted = bright_img
    else:
        # Pillow derives the contrast pivot after brightness has clipped
        # and rounded, so the combined table must use that intermediate.
        pivot = int(PIL.ImageStat.Stat(bright_img.convert("L")).mean[0] + 0.5)
        contrast_ramp = PIL.Image.blend(
            PIL.Image.new("L", ramp.size, pivot), bright_ramp, spread
        )
        contrast_lut = list(contrast_ramp.tobytes())
        adjusted = img.point(contrast_lut * 3 + alpha_lut)

    image_format = (
        QImage.Format.Format_RGBA8888
        if adjusted.mode == "RGBA"
        else QImage.Format.Format_RGB888
    )
    return QImage(
        adjusted.tobytes(),
        adjusted.width,
        adjusted.height,
        adjusted.width * len(adjusted.getbands()),
        image_format,
    )


def _as_percent(*, value: int) -> str:
    return f"{value}%"
