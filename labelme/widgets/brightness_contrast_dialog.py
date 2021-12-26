from codecs import utf_16_be_decode
import PIL.Image
import PIL.ImageEnhance
from PIL import ImageFilter
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
        self.apply_filter_checkbox = self._create_checkbox(self.connect_filter_Checkbox,"Gauss")

        formLayout = QtWidgets.QFormLayout()
        formLayout.addRow(self.tr("Brightness"), self.slider_brightness)
        formLayout.addRow(self.tr("Contrast"), self.slider_contrast)
        formLayout.addRow(self.tr("Filter Options"),self.apply_filter_checkbox)
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
        self._apply_change(img)
        
    def apply_filter(self):
    
        img = self.img
        img = img.filter(ImageFilter.GaussianBlur)
        self._apply_change(img)

    def connect_filter_Checkbox(self,checked):
        #checked = self.apply_filter_checkbox.isChecked()
        if checked:
            self.apply_filter()
        else:
            self.get_unprocessed_image()


    def get_unprocessed_image(self):
        self._apply_change(self.img)

    def _create_slider(self):
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(0, 150)
        slider.setValue(50)
        slider.valueChanged.connect(self.onNewValue)
        return slider

    def _create_checkbox(self,stateCallback,cbText):
        assert isinstance(cbText,str),"type is not strinf"
        checkbox = QtWidgets.QCheckBox(cbText)
        checkbox.stateChanged.connect(stateCallback)
        return checkbox

    def _apply_change(self,img):
        img_data = utils.img_pil_to_data(img)
        qimage = QtGui.QImage.fromData(img_data)
        self.callback(qimage)
    