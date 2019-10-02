from qtpy import QtWidgets,QtGui
from qtpy.QtCore import Qt

from PIL import Image, ImageEnhance
import io

class AdjustBrightnessContrastWidget(QtWidgets.QDialog):
    def __init__(self, filename, callback, parent=None):
        super(AdjustBrightnessContrastWidget, self).__init__(parent)
        self.setModal(True)
        self.setWindowTitle('Brightness/Contrast')

        self.slider0 = self._create_slider()
        self.slider1 = self._create_slider()

        formLayout   = QtWidgets.QFormLayout()
        formLayout.addRow(self.tr('Brightness'), self.slider0)
        formLayout.addRow(self.tr('Contrast'),   self.slider1)
        self.setLayout(formLayout)

        self.img = Image.open(filename).convert('RGBA')
        self.callback = callback

    def onNewValue(self, value):
        brightness, contrast = self.slider0.value()/100, self.slider1.value()/100

        img  = self.img
        img  = ImageEnhance.Brightness(img).enhance(brightness)
        img  = ImageEnhance.Contrast(img).enhance(contrast)

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
