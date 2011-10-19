
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from lib import newButton, labelValidator

BB = QDialogButtonBox

class SimpleLabelDialog(QDialog):

    def __init__(self, text="Enter object label", parent=None):
        super(SimpleLabelDialog, self).__init__(parent)
        self.edit = QLineEdit()
        self.edit.setText(text)
        self.edit.setValidator(labelValidator())
        self.edit.editingFinished.connect(self.postProcess)
        layout = QVBoxLayout()
        layout.addWidget(self.edit)
        self.buttonBox = bb = BB(BB.Ok | BB.Cancel, Qt.Horizontal, self)
        bb.accepted.connect(self.validate)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.setLayout(layout)

    def validate(self):
        if self.edit.text().trimmed():
            self.accept()

    def postProcess(self):
        self.edit.setText(self.edit.text().trimmed())

    def popUp(self, text='', position=None):
        self.edit.setText(text)
        self.edit.setSelection(0, len(text))
        self.edit.setFocus(Qt.PopupFocusReason)
        if position is not None:
            self.move(position)
        return self.edit.text() if self.exec_() else None

    def text(self):
        return self.edit.text()

