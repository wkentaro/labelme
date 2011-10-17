
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from lib import newButton, labelValidator

BB = QDialogButtonBox

class SimpleLabelDialog(QDialog):

    def __init__(self, text='', parent=None):
        super(SimpleLabelDialog, self).__init__(parent)
        self.edit = QLineEdit()
        self.edit.setText(text)
        self.edit.setValidator(labelValidator())
        self.edit.editingFinished.connect(self.postProcess)
        layout = QVBoxLayout()
        layout.addWidget(self.edit)
        bb = BB(BB.Ok | BB.Cancel, Qt.Horizontal, self)
        bb.accepted.connect(self.validate)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.setLayout(layout)

    def validate(self):
        if self.edit.text().trimmed():
            self.accept()

    def postProcess(self):
        self.edit.setText(self.edit.text().trimmed())

    def popUp(self, text='', pos=None):
        self.edit.setText(text)
        self.edit.setSelection(0, len(text))
        self.edit.setFocus(Qt.PopupFocusReason)
        if pos is not None:
            self.move(pos)
        return self.edit.text() if self.exec_() else None

