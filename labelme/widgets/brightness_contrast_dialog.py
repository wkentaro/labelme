import PIL.Image
import PIL.ImageEnhance
from PIL import ImageFilter
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QSpinBox, QWidget
from numpy import array
from qtpy.QtCore import Qt
from qtpy import QtGui
from qtpy import QtWidgets
import numpy as np
import cv2
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
        self.normalize_pushButton = self._create_pushButton(self.call_normalize,"normalize")
        self.reset_pushButton = self._create_pushButton(self.reset,"reset processing")
        self.kernelSize = self._create_spinBox(min_val=3,max_val=7,step=2)
        self.kernelSize.valueChanged.connect (self.apply_sobel_filter)
        self.derivative = self._create_spinBox(min_val=1,max_val=3)
        self.derivative.valueChanged.connect (self.apply_sobel_filter)
        self.HasReset = True 

        formLayout = QtWidgets.QFormLayout()
        formLayout.addRow(self.tr("Brightness"), self.slider_brightness)
        formLayout.addRow(self.tr("Contrast"), self.slider_contrast)
        formLayout.addRow(self.tr("Filter Options"),self.apply_gauss_filter_checkbox)
        formLayout.addRow(self.tr(""),self.apply_sobel_filter_checkbox)
        formLayout.addRow(self.tr("kernel size"),self.kernelSize)
        formLayout.addRow(self.tr("derivative size"),self.derivative)
        formLayout.addRow(self.tr(""), self.normalize_pushButton)
        formLayout.addRow(self.tr(""), self.reset_pushButton)

        self.setLayout(formLayout)

        assert isinstance(img, PIL.Image.Image)
        self.img = img
        self.callback = callback

    def brightness_contrast_transform(self):
        brightness = self.slider_brightness.value() - 50
        contrast = self.slider_contrast.value() / 50
        img_np = np.array(self.img)
        #img = self.img
        #if img.mode != "L":
        #    img = img.convert("L")
        #img = PIL.ImageEnhance.Brightness(img).enhance(brightness)
        #img = PIL.ImageEnhance.Contrast(img).enhance(contrast)
        if brightness < 0:
            img_np = cv2.subtract(img_np,-1*brightness)
        img = cv2.convertScaleAbs(img_np,alpha=contrast,beta= max(0,brightness))
        
        self.HasReset = False
        return img

    def call_normalize(self):
        img = self.brightness_contrast_transform()
        img_t = utils.image.normalize_image(img)
        self.HasReset=False
        self._apply_change(img_t)
        
    
    def reset(self):
        self.slider_brightness.setValue(50)
        self.slider_contrast.setValue(50)
        self.HasReset = True
        self._apply_change(self.img)

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
        img = cv2.Sobel(img,cv2.CV_8U,dx=self.derivative.value(),dy=self.derivative.value(),ksize=self.kernelSize.value())
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

    def _create_spinBox(self,min_val,max_val,step=1):
        spinBox = QSpinBox()
        spinBox.setMaximum(max_val)
        spinBox.setMinimum(min_val)
        spinBox.setSingleStep(step)
        return spinBox


    def _apply_change(self,img):
        if isinstance(img,PIL.Image.Image):
            img_data = utils.img_pil_to_data(img)
            qimage = QtGui.QImage.fromData(img_data)
        elif isinstance(img,np.ndarray):    
            qimage = QtGui.QImage(img.data, img.shape[1], img.shape[0],QImage.Format_Indexed8)
        self.callback(qimage)
    