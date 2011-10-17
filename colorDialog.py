
from PyQt4.QtGui import *
from PyQt4.QtCore import *

class ColorDialog(QColorDialog):
    def __init__(self, parent=None):
        super(ColorDialog, self).__init__(parent)
        self.setOption(QColorDialog.ShowAlphaChannel)

    def getColor(self, value=None, title=None):
        if title:
            self.setWindowTitle(title)
        if value:
            self.setCurrentColor(value)
        return self.currentColor() if self.exec_() else None

