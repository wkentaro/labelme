
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from lib import newIcon
from simpleLabelDialog import SimpleLabelDialog

BB = QDialogButtonBox

class LabelDialog(SimpleLabelDialog):
    def __init__(self, parent=None):
        super(LabelDialog, self).__init__(parent=parent)
        self.buttonBox.button(BB.Ok).setIcon(newIcon('done'))
        self.buttonBox.button(BB.Cancel).setIcon(newIcon('undo'))

