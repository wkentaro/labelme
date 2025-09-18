import PIL.Image
import PIL.ImageEnhance
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage


class BrightnessContrastDialog(QtWidgets.QDialog):
    _base_value = 50

    img: PIL.Image.Image

    def __init__(self, img: PIL.Image.Image, callback, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Brightness/Contrast")

        sliders = {}
        layouts = {}
        for title in ["Brightness:", "Contrast:"]:
            layout = QtWidgets.QHBoxLayout()
            title_label = QtWidgets.QLabel(self.tr(title))
            title_label.setFixedWidth(75)
            layout.addWidget(title_label)
            #
            slider = QtWidgets.QSlider(Qt.Horizontal)
            slider.setRange(0, 3 * self._base_value)
            slider.setValue(self._base_value)
            layout.addWidget(slider)
            #
            value_label = QtWidgets.QLabel(f"{slider.value() / self._base_value:.2f}")
            value_label.setAlignment(Qt.AlignRight)
            layout.addWidget(value_label)
            #
            slider.valueChanged.connect(self.onNewValue)
            slider.valueChanged.connect(
                lambda _,
                value_label_=value_label,
                slider_=slider: value_label_.setText(
                    f"{slider_.value() / self._base_value:.2f}"
                )
            )
            layouts[title] = layout
            sliders[title] = slider

        self.slider_brightness = sliders["Brightness:"]
        self.slider_contrast = sliders["Contrast:"]
        del sliders

        v_layout = QtWidgets.QVBoxLayout()
        v_layout.addLayout(layouts["Brightness:"])
        v_layout.addLayout(layouts["Contrast:"])
        del layouts
        self.setLayout(v_layout)

        if img.mode != "RGB":
            raise ValueError("Image mode must be RGB")
        self.img = img
        self.callback = callback

    def onNewValue(self, _):
        brightness = self.slider_brightness.value() / self._base_value
        contrast = self.slider_contrast.value() / self._base_value

        img: PIL.Image.Image = self.img
        if brightness != 1:
            img = PIL.ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1:
            img = PIL.ImageEnhance.Contrast(img).enhance(contrast)

        qimage = QImage(
            img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888
        )
        self.callback(qimage)
