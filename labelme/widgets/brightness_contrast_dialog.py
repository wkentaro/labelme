from __future__ import annotations

from collections.abc import Callable

import PIL.Image
import PIL.ImageEnhance
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage


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
        self.setModal(True)
        self.setWindowTitle("Brightness/Contrast")

        slider_map: dict[str, QtWidgets.QSlider] = {}
        row_layouts: dict[str, QtWidgets.QHBoxLayout] = {}
        for label_text in ("Brightness:", "Contrast:"):
            row = QtWidgets.QHBoxLayout()
            name_label = QtWidgets.QLabel(self.tr(label_text))
            name_label.setFixedWidth(75)
            row.addWidget(name_label)

            slider = QtWidgets.QSlider(Qt.Horizontal)
            slider.setRange(0, 3 * self._base_value)
            slider.setValue(self._base_value)
            row.addWidget(slider)

            val_label = QtWidgets.QLabel(
                f"{slider.value() / self._base_value:.2f}"
            )
            val_label.setAlignment(Qt.AlignRight)
            row.addWidget(val_label)

            slider.valueChanged.connect(self.onNewValue)
            slider.valueChanged.connect(
                lambda _,
                vl=val_label,
                sl=slider: vl.setText(
                    f"{sl.value() / self._base_value:.2f}"
                )
            )
            row_layouts[label_text] = row
            slider_map[label_text] = slider

        self.slider_brightness = slider_map["Brightness:"]
        self.slider_contrast = slider_map["Contrast:"]

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(row_layouts["Brightness:"])
        main_layout.addLayout(row_layouts["Contrast:"])
        self.setLayout(main_layout)

        self._alpha = None
        if "A" in img.getbands():
            self._alpha = img.getchannel("A")
        if img.mode != "RGB":
            img = img.convert("RGB")
        self.img = img
        self.callback = callback

    def onNewValue(self, _: int | None) -> None:
        brightness_ratio = self.slider_brightness.value() / self._base_value
        contrast_ratio = self.slider_contrast.value() / self._base_value

        adjusted: PIL.Image.Image = self.img
        if brightness_ratio != 1:
            adjusted = PIL.ImageEnhance.Brightness(adjusted).enhance(brightness_ratio)
        if contrast_ratio != 1:
            adjusted = PIL.ImageEnhance.Contrast(adjusted).enhance(contrast_ratio)

        fmt: QImage.Format
        if self._alpha is None:
            fmt = QImage.Format_RGB888
        else:
            adjusted = adjusted.convert("RGBA")
            adjusted.putalpha(self._alpha)
            fmt = QImage.Format_RGBA8888

        num_channels = len(adjusted.getbands())
        qimage = QImage(
            adjusted.tobytes(),
            adjusted.width,
            adjusted.height,
            adjusted.width * num_channels,
            fmt,
        )
        self.callback(qimage)
