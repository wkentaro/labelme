import PIL.Image
import PIL.ImageEnhance
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage


class BrightnessContrastDialog(QtWidgets.QDialog):
    _base_value = 50

    def __init__(self, img, callback, parent=None):
        super(BrightnessContrastDialog, self).__init__(parent)
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
            slider = QtWidgets.QSlider(Qt.Horizontal)  # type: ignore[attr-defined]
            slider.setRange(0, 3 * self._base_value)
            slider.setValue(self._base_value)
            layout.addWidget(slider)
            #
            value_label = QtWidgets.QLabel(f"{slider.value() / self._base_value:.2f}")
            value_label.setAlignment(Qt.AlignRight)  # type: ignore[attr-defined]
            layout.addWidget(value_label)
            #

            #EDITED BRIGHTNESS
            slider.valueChanged.connect(
                lambda value, s=slider, l=value_label: l.setText(f"{s.value() / self._base_value:.2f}")
            )
            slider.sliderReleased.connect(self.onNewValue)
    
            #END

            # slider.valueChanged.connect(self.onNewValue)
            # slider.valueChanged.connect(
            #     lambda: value_label.setText(f"{slider.value() / self._base_value:.2f}")
            # )

            layouts[title] = layout
            sliders[title] = slider

        self.slider_brightness = sliders["Brightness:"]
        self.slider_contrast = sliders["Contrast:"]
        del sliders

        layout = QtWidgets.QVBoxLayout()  # type: ignore[assignment]
        layout.addLayout(layouts["Brightness:"])
        layout.addLayout(layouts["Contrast:"])
        del layouts

        #EDITED BRIGHTNESS
        # Add Reset button
        button_layout = QtWidgets.QHBoxLayout()
        reset_button = QtWidgets.QPushButton("Reset")
        reset_button.clicked.connect(self.resetValues)
        button_layout.addStretch()
        button_layout.addWidget(reset_button)
        layout.addLayout(button_layout)
        #END

        self.setLayout(layout)

        assert isinstance(img, PIL.Image.Image)
        self.img = img
        self.callback = callback

    def onNewValue(self, _=None):
        brightness = self.slider_brightness.value() / self._base_value
        contrast = self.slider_contrast.value() / self._base_value

        #EDITED BRIGHTNESS
        img = self.img.copy()
        #END

        # img = self.img
        if brightness != 1:
            img = PIL.ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1:
            img = PIL.ImageEnhance.Contrast(img).enhance(contrast)

        #EDITED BRIGHTNESS
        img = img.convert("RGB")
        #END

        qimage = QImage(
            img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888
        )
        self.callback(qimage)

    #EDITED BRIGHTNESS
    def resetValues(self):
        self.slider_brightness.setValue(self._base_value)
        self.slider_contrast.setValue(self._base_value)

        # Reset image to original
        img = self.img.copy().convert("RGB")
        qimage = QImage(
            img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888
        )
        if not qimage.isNull():
            self.callback(qimage)

    def setImage(self, img):
        """Called when a new image is loaded — updates the dialog's base image."""
        self.img = img
        # Re-apply current brightness/contrast to the new image
        self.onNewValue()

    #END