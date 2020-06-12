from qtpy.QtCore import Qt
from qtpy import QtGui
from qtpy import QtWidgets

from PIL import Image
from PIL import ImageEnhance


class BrightnessContrastDialog(QtWidgets.QDialog):
    def __init__(self, filename, callback, parent=None):
        super(BrightnessContrastDialog, self).__init__(parent)
        self.setModal(True)
        self.setWindowTitle('Brightness/Contrast')

        self.slider_brightness = self._create_slider()
        self.slider_contrast = self._create_slider()

        formLayout = QtWidgets.QFormLayout()
        formLayout.addRow(self.tr('Brightness'), self.slider_brightness)
        formLayout.addRow(self.tr('Contrast'), self.slider_contrast)
        self.setLayout(formLayout)

        self.img = Image.open(filename).convert('RGBA')
        self.callback = callback

    def onNewValue(self, value):
        brightness = self.slider_brightness.value() / 100.
        contrast = self.slider_contrast.value() / 100.

        img = self.img
        img = ImageEnhance.Brightness(img).enhance(brightness)
        img = ImageEnhance.Contrast(img).enhance(contrast)

        bytes = img.tobytes('raw', 'RGBA')
        qimage = QtGui.QImage(bytes,
                              img.size[0], img.size[1],
                              QtGui.QImage.Format_RGB32).rgbSwapped()
        self.callback(qimage)

    def _create_slider(self):
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(0, 300)
        slider.setValue(100)
        slider.valueChanged.connect(self.onNewValue)
        return slider
