
from PyQt4.QtGui import *
from PyQt4.QtCore import *

class ZoomWidget(QSpinBox):
    def __init__(self, value=100):
        super(ZoomWidget, self).__init__()
        self.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        self.setRange(1, 500)
        self.setSuffix(' %')
        self.setValue(value)
        self.setToolTip(u'Image zoom')
        self.setStatusTip(self.toolTip())

