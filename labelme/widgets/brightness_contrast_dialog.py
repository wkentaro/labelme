import PIL.Image
import PIL.ImageEnhance
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtGui import QImage


class BrightnessContrastDialog(QtWidgets.QDialog):
    _base_value = 50

    def __init__(self, img, callback, parent=None):
        super(BrightnessContrastDialog, self).__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Brightness/Contrast")

        self.slider_brightness, widget_brightness = self._create_slider()
        self.slider_contrast, widget_contrast = self._create_slider()

        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow(self.tr("Brightness"), widget_brightness)
        form_layout.addRow(self.tr("Contrast"), widget_contrast)
        self.setLayout(form_layout)

        assert isinstance(img, PIL.Image.Image)
        self.img = img
        self.callback = callback

    def onNewValue(self, _):
        brightness = self.slider_brightness.value() / self._base_value
        contrast = self.slider_contrast.value() / self._base_value

        img = self.img
        if brightness != 1:
            img = PIL.ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1:
            img = PIL.ImageEnhance.Contrast(img).enhance(contrast)

        qimage = QImage(
            img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888
        )
        self.callback(qimage)

    def _create_slider(self):
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(0, 3 * self._base_value)
        slider.setValue(self._base_value)
        slider.valueChanged.connect(self.onNewValue)
        value_label = QtWidgets.QLabel(f"{slider.value() / self._base_value:.2f}")
        slider.valueChanged.connect(
            lambda value: value_label.setText(f"{value / self._base_value:.2f}")
        )
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(slider)
        layout.addWidget(value_label)
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return slider, widget
