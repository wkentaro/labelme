import PIL.Image
import PIL.ImageEnhance
from qtpy.QtCore import Qt
from qtpy import QtGui
from qtpy import QtWidgets

from .. import utils


class BrightnessContrastDialog(QtWidgets.QDialog):
    def __init__(self, img, callback, parent=None):
        super(BrightnessContrastDialog, self).__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Brightness/Contrast")

        self.slider_brightness = self._create_slider()
        self.slider_contrast = self._create_slider()

        formLayout = QtWidgets.QFormLayout()
        formLayout.addRow(self.tr("Brightness"), self.slider_brightness)
        formLayout.addRow(self.tr("Contrast"), self.slider_contrast)
        self.setLayout(formLayout)

        assert isinstance(img, PIL.Image.Image)
        self.img = img
        self.callback = callback

    def onNewValue(self, value):
        brightness = self.slider_brightness.value() / 50.0
        contrast = self.slider_contrast.value() / 50.0

        img = self.img
        img = PIL.ImageEnhance.Brightness(img).enhance(brightness)
        img = PIL.ImageEnhance.Contrast(img).enhance(contrast)

        img_data = utils.img_pil_to_data(img)
        qimage = QtGui.QImage.fromData(img_data)
        self.callback(qimage)

    def _create_slider(self):
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(0, 150)
        slider.setValue(50)
        slider.valueChanged.connect(self.onNewValue)
        return slider
