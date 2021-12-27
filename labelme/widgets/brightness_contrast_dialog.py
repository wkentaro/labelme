import PIL.Image
import PIL.ImageEnhance
from PIL import ImageFilter
from qtpy.QtCore import Qt
from qtpy import QtGui
from qtpy import QtWidgets
import numpy as np
from cv2 import normalize, NORM_MINMAX,CV_32F
from .. import utils


class BrightnessContrastDialog(QtWidgets.QDialog):
    def __init__(self, img, callback, parent=None):
        super(BrightnessContrastDialog, self).__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Brightness/Contrast")

        self.slider_brightness = self._create_slider()
        self.slider_contrast = self._create_slider()
        self.apply_gauss_filter_checkbox = self._create_checkbox(self.connect_gauss_filter_Checkbox,"Gauss")
        self.apply_sobel_filter_checkbox = self._create_checkbox(self.connect_sobel_filter_Checkbox,"Sobel")
        self.normalize_pushButton = self._create_pushButton(self.normalize_image,"normalize")

        formLayout = QtWidgets.QFormLayout()
        formLayout.addRow(self.tr("Brightness"), self.slider_brightness)
        formLayout.addRow(self.tr("Contrast"), self.slider_contrast)
        formLayout.addRow(self.tr(""), self.normalize_pushButton)
        formLayout.addRow(self.tr("Filter Options"),self.apply_gauss_filter_checkbox)
        formLayout.addRow(self.tr(""),self.apply_sobel_filter_checkbox)

        self.setLayout(formLayout)

        assert isinstance(img, PIL.Image.Image)
        self.img = img
        self.callback = callback

    def brightness_contrast_transform(self):
        brightness = self.slider_brightness.value() / 50.0
        contrast = self.slider_contrast.value() / 50.0

        img = self.img
        img = PIL.ImageEnhance.Brightness(img).enhance(brightness)
        img = PIL.ImageEnhance.Contrast(img).enhance(contrast)
        return img

    def normalize_image(self):
        img = self.brightness_contrast_transform()
        np_img = np.array(img)
        np_img = normalize(np_img, None, alpha=0, beta=1, norm_type=NORM_MINMAX, dtype=CV_32F)*255
        img_t = PIL.Image.fromarray(np_img.astype("uint8"),mode="L")
        self._apply_change(img_t)
    @staticmethod
    def _create_pushButton(callback,buttonText):
        button = QtWidgets.QPushButton(buttonText)
        button.clicked.connect(callback)
        return button


    def onNewValue(self):
        img = self.brightness_contrast_transform()
        self._apply_change(img)
        
    def apply_gauss_filter(self):
        img = self.brightness_contrast_transform()
        img = img.filter(ImageFilter.GaussianBlur)
        self._apply_change(img)

    def connect_gauss_filter_Checkbox(self,checked):
        #checked = self.apply_gauss_filter_checkbox.isChecked()
        if checked:
            self.apply_gauss_filter()
        else:
            self.get_unprocessed_image()

    def connect_sobel_filter_Checkbox(self,checked):
        if checked:
            self.apply_sobel_filter()
        else:
            self.get_unprocessed_image()

    def apply_sobel_filter(self):
        img = self.brightness_contrast_transform()
        img = img.filter(ImageFilter.FIND_EDGES)
        self._apply_change(img)

    def get_unprocessed_image(self):
        img = self.brightness_contrast_transform()
        self._apply_change(img)

    def _create_slider(self):
        slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(0, 150)
        slider.setValue(50)
        slider.valueChanged.connect(self.onNewValue)
        return slider

    def _create_checkbox(self,stateCallback,cbText):
        assert isinstance(cbText,str),"type is not string"
        checkbox = QtWidgets.QCheckBox(cbText)
        checkbox.stateChanged.connect(stateCallback)
        return checkbox

    def _apply_change(self,img):
        img_data = utils.img_pil_to_data(img)
        qimage = QtGui.QImage.fromData(img_data)
        self.callback(qimage)
    