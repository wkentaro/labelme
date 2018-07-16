from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets


class ZoomWidget(QtWidgets.QSpinBox):

    def __init__(self, zmax=25000, value=100):
        super(ZoomWidget, self).__init__()
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        #zmax = 25000
        self.setRange(1, zmax)
        self.setSuffix(' %')
        self.setValue(value)
        self.setToolTip('Zoom Level')
        self.setStatusTip(self.toolTip())
        self.setAlignment(QtCore.Qt.AlignCenter)

    def minimumSizeHint(self):
        height = super(ZoomWidget, self).minimumSizeHint().height()
        fm = QtGui.QFontMetrics(self.font())
        width = fm.width(str(self.maximum()))
        return QtCore.QSize(width, height)

class FileNumWidget(QtWidgets.QSpinBox):

    def __init__(self, nmax=1, value=1):
        super(FileNumWidget, self).__init__()
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.nmax = nmax
        self.setRange(-nmax, nmax)
        self.setSuffix(' .')
        self.setValue(value)
        self.setToolTip('File num')
        self.setStatusTip(self.toolTip())
        self.setAlignment(QtCore.Qt.AlignCenter)

    def minimumSizeHint(self):
        height = super(FileNumWidget, self).minimumSizeHint().height()
        fm = QtGui.QFontMetrics(self.font())
        width = fm.width(str(self.maximum()))
        return QtCore.QSize(width, height)

    def setMax(self,nmax):
        self.nmax = nmax
        self.setRange(-nmax,nmax)

    def getMax(self):
        return self.nmax

