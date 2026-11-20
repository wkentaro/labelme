from __future__ import annotations

from collections.abc import Callable
from typing import Final

import numpy as np
import PIL.Image
import PIL.ImageEnhance
import PIL.ImageStat
from numpy.typing import NDArray
from PySide6 import QtCore
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from .. import _dicom

_NEUTRAL: Final = 100


class BrightnessContrastDialog(QtWidgets.QDialog):
    _publish: Callable[[QImage], None]
    _on_dicom_window_changed: Callable[[float, float, bool, str], None] | None
    _img: PIL.Image.Image
    _hu_array: NDArray[np.float32] | None
    _auto_window_center: float
    _auto_window_width: float
    _default_invert: bool

    slider_brightness: QtWidgets.QSlider
    slider_contrast: QtWidgets.QSlider

    combo_preset: QtWidgets.QComboBox
    spin_window_center: QtWidgets.QDoubleSpinBox
    slider_window_center: QtWidgets.QSlider
    spin_window_width: QtWidgets.QDoubleSpinBox
    slider_window_width: QtWidgets.QSlider
    check_invert: QtWidgets.QCheckBox

    def __init__(
        self,
        *,
        img: PIL.Image.Image,
        callback: Callable[[QImage], None],
        brightness: int | None = None,
        contrast: int | None = None,
        hu_array: NDArray[np.float32] | None = None,
        window_center: float | None = None,
        window_width: float | None = None,
        invert: bool = False,
        preset_name: str = "auto",
        default_window_center: float | None = None,
        default_window_width: float | None = None,
        default_invert: bool = False,
        on_dicom_window_changed: Callable[[float, float, bool, str], None]
        | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Brightness/Contrast"))
        self._publish = callback
        self._on_dicom_window_changed = on_dicom_window_changed
        self._hu_array = hu_array
        self._default_invert = default_invert

        self._img = _to_adjustable(img=img)
        self.slider_brightness = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.slider_contrast = QtWidgets.QSlider(Qt.Orientation.Horizontal)

        self.combo_preset = QtWidgets.QComboBox()
        self.spin_window_center = QtWidgets.QDoubleSpinBox()
        self.slider_window_center = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.spin_window_width = QtWidgets.QDoubleSpinBox()
        self.slider_window_width = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.check_invert = QtWidgets.QCheckBox("Invert Monochrome")

        if hu_array is not None:
            self._init_dicom_ui(
                hu_array=hu_array,
                window_center=window_center,
                window_width=window_width,
                invert=invert,
                preset_name=preset_name,
                default_window_center=default_window_center,
                default_window_width=default_window_width,
            )
            return

        self._auto_window_center = 0.0
        self._auto_window_width = 255.0

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

    def _init_dicom_ui(
        self,
        *,
        hu_array: NDArray[np.float32],
        window_center: float | None,
        window_width: float | None,
        invert: bool,
        preset_name: str,
        default_window_center: float | None,
        default_window_width: float | None,
    ) -> None:
        MIN_HU_BOUND: Final[float] = -2048.0
        MAX_HU_BOUND: Final[float] = 4096.0
        MAX_WW_BOUND: Final[float] = 6000.0

        if default_window_center is not None and default_window_width is not None:
            auto_wc = float(default_window_center)
            auto_ww = max(float(default_window_width), 1.0)
        else:
            auto_wc, auto_ww = _dicom.compute_auto_window(hu_array=hu_array)
        self._auto_window_center = auto_wc
        self._auto_window_width = auto_ww

        init_wc = auto_wc if window_center is None else float(window_center)
        init_ww = max(auto_ww if window_width is None else float(window_width), 1.0)

        finite = hu_array[np.isfinite(hu_array)]
        hu_min = float(finite.min()) if finite.size > 0 else MIN_HU_BOUND
        hu_max = float(finite.max()) if finite.size > 0 else MAX_HU_BOUND

        wc_min = min(hu_min, MIN_HU_BOUND, init_wc)
        wc_max = max(hu_max, MAX_HU_BOUND, init_wc)
        ww_max = max(hu_max - hu_min, MAX_WW_BOUND, init_ww)

        for key in (*_dicom.DICOM_WINDOW_PRESETS.keys(), "custom"):
            self.combo_preset.addItem(key, key)

        if preset_name in _dicom.DICOM_WINDOW_PRESETS or preset_name == "custom":
            self.combo_preset.setCurrentText(preset_name)
        else:
            self.combo_preset.setCurrentText("auto")

        self.spin_window_center.setDecimals(1)
        self.spin_window_center.setRange(wc_min, wc_max)
        self.spin_window_center.setSingleStep(10.0)
        self.spin_window_center.setValue(init_wc)

        self.slider_window_center.setRange(round(wc_min), round(wc_max))
        self.slider_window_center.setSingleStep(5)
        self.slider_window_center.setPageStep(50)
        self.slider_window_center.setValue(round(init_wc))

        self.spin_window_width.setDecimals(1)
        self.spin_window_width.setRange(1.0, ww_max)
        self.spin_window_width.setSingleStep(10.0)
        self.spin_window_width.setValue(init_ww)

        self.slider_window_width.setRange(1, round(ww_max))
        self.slider_window_width.setSingleStep(5)
        self.slider_window_width.setPageStep(50)
        self.slider_window_width.setValue(round(init_ww))

        self.check_invert.setChecked(invert)

        self.combo_preset.currentTextChanged.connect(self._on_preset_changed)
        self.spin_window_center.valueChanged.connect(self._on_spin_wc_changed)
        self.slider_window_center.valueChanged.connect(self._on_slider_wc_changed)
        self.spin_window_width.valueChanged.connect(self._on_spin_ww_changed)
        self.slider_window_width.valueChanged.connect(self._on_slider_ww_changed)
        self.check_invert.toggled.connect(lambda _checked: self.apply())

        grid = QtWidgets.QGridLayout(self)
        grid.setColumnStretch(1, 1)

        label_preset = QtWidgets.QLabel("Preset:")
        label_preset.setBuddy(self.combo_preset)
        grid.addWidget(label_preset, 0, 0)
        grid.addWidget(self.combo_preset, 0, 1, 1, 2)

        label_wc = QtWidgets.QLabel("Window Center (WL):")
        label_wc.setBuddy(self.slider_window_center)
        grid.addWidget(label_wc, 1, 0)
        grid.addWidget(self.slider_window_center, 1, 1)
        grid.addWidget(self.spin_window_center, 1, 2)

        label_ww = QtWidgets.QLabel("Window Width (WW):")
        label_ww.setBuddy(self.slider_window_width)
        grid.addWidget(label_ww, 2, 0)
        grid.addWidget(self.slider_window_width, 2, 1)
        grid.addWidget(self.spin_window_width, 2, 2)

        grid.addWidget(self.check_invert, 3, 0, 1, 3)

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
        grid.addWidget(buttons, 4, 0, 1, 3)
        self.setMinimumWidth(420)

    @property
    def window_center(self) -> float:
        return float(self.spin_window_center.value())

    @property
    def window_width(self) -> float:
        return float(self.spin_window_width.value())

    @property
    def is_inverted(self) -> bool:
        return bool(self.check_invert.isChecked())

    @property
    def preset_name(self) -> str:
        return self.combo_preset.currentText() or "auto"

    def _set_wc_ww_controls(self, *, wc: float, ww: float) -> None:
        with (
            QtCore.QSignalBlocker(self.spin_window_center),
            QtCore.QSignalBlocker(self.slider_window_center),
            QtCore.QSignalBlocker(self.spin_window_width),
            QtCore.QSignalBlocker(self.slider_window_width),
        ):
            self.spin_window_center.setValue(wc)
            self.slider_window_center.setValue(round(wc))
            self.spin_window_width.setValue(ww)
            self.slider_window_width.setValue(round(ww))

    def _sync_preset_to_values(self) -> None:
        PRESET_MATCH_EPSILON: Final[float] = 1e-3

        wc = self.window_center
        ww = self.window_width
        matched = "custom"
        for key, pair in _dicom.DICOM_WINDOW_PRESETS.items():
            if pair is None:
                continue
            if (
                abs(wc - pair[0]) < PRESET_MATCH_EPSILON
                and abs(ww - pair[1]) < PRESET_MATCH_EPSILON
            ):
                matched = key
                break
        with QtCore.QSignalBlocker(self.combo_preset):
            self.combo_preset.setCurrentText(matched)

    def _on_preset_changed(self, preset_key: str, /) -> None:
        if preset_key == "auto":
            self._set_wc_ww_controls(
                wc=self._auto_window_center, ww=self._auto_window_width
            )
            self.apply()
            return
        pair = _dicom.DICOM_WINDOW_PRESETS.get(preset_key)
        if pair is not None:
            self._set_wc_ww_controls(wc=pair[0], ww=pair[1])
            self.apply()

    def _on_spin_wc_changed(self, value: float, /) -> None:
        with QtCore.QSignalBlocker(self.slider_window_center):
            self.slider_window_center.setValue(round(value))
        self._sync_preset_to_values()
        self.apply()

    def _on_slider_wc_changed(self, value: int, /) -> None:
        with QtCore.QSignalBlocker(self.spin_window_center):
            self.spin_window_center.setValue(float(value))
        self._sync_preset_to_values()
        self.apply()

    def _on_spin_ww_changed(self, value: float, /) -> None:
        with QtCore.QSignalBlocker(self.slider_window_width):
            self.slider_window_width.setValue(round(value))
        self._sync_preset_to_values()
        self.apply()

    def _on_slider_ww_changed(self, value: int, /) -> None:
        with QtCore.QSignalBlocker(self.spin_window_width):
            self.spin_window_width.setValue(float(value))
        self._sync_preset_to_values()
        self.apply()

    def _restore_defaults(self) -> None:
        if self._hu_array is not None:
            with (
                QtCore.QSignalBlocker(self.combo_preset),
                QtCore.QSignalBlocker(self.check_invert),
            ):
                self.combo_preset.setCurrentText("auto")
                self.check_invert.setChecked(self._default_invert)
            self._set_wc_ww_controls(
                wc=self._auto_window_center, ww=self._auto_window_width
            )
            self.apply()
            return
        self.slider_brightness.setValue(_NEUTRAL)
        self.slider_contrast.setValue(_NEUTRAL)

    def apply(self) -> None:
        if self._hu_array is not None:
            wc = self.window_center
            ww = self.window_width
            inv = self.is_inverted
            preset = self.preset_name
            if self._on_dicom_window_changed is not None:
                self._on_dicom_window_changed(wc, ww, inv, preset)
            arr_u8 = _dicom.apply_dicom_window(
                hu_array=self._hu_array,
                window_center=wc,
                window_width=ww,
                invert=inv,
            )
            img = PIL.Image.fromarray(arr_u8, mode="L").convert("RGB")
            qimage = QImage(
                img.tobytes(),
                img.width,
                img.height,
                img.width * 3,
                QImage.Format.Format_RGB888,
            ).copy()
            self._publish(qimage)
            return

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
