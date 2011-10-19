
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from lib import newButton, labelValidator

# FIXME:
# - Use the validator when accepting the dialog.

class LabelDialog(QDialog):
    OK, UNDO, DELETE = range(3)

    def __init__(self, text='', parent=None):
        super(LabelDialog, self).__init__(parent)
        self.setWindowTitle("Enter object's label")
        self.action = self.OK
        self.edit = QLineEdit()
        self.edit.setText(text)
        self.edit.setValidator(labelValidator())
        self.edit.editingFinished.connect(self.postProcess)
        layout = QVBoxLayout()
        layout.addWidget(self.edit)
        done = newButton('done', icon='done', slot=self.validate)
        delete = newButton('delete', icon='delete', slot=self.delete)
        undo = newButton('undo close', icon='undo', slot=self.undo)
        bb = QHBoxLayout()
        for btn in done, undo, delete:
            bb.addWidget(btn)
        layout.addLayout(bb)
        self.setLayout(layout)

    def undo(self):
        self.action = self.UNDO
        self.reject()

    def delete(self):
        self.action = self.DELETE
        self.reject()

    def text(self):
        return self.edit.text()

    def popUp(self, text='', position=None):
        # It actually works without moving...
        self.move(position)
        self.edit.setText(text)
        self.edit.setSelection(0, len(self.edit.text()))
        self.edit.setFocus(Qt.PopupFocusReason)
        return self.OK if self.exec_() == QDialog.Accepted else self.action

    def validate(self):
        if self.edit.text().trimmed():
            self.accept()

    def postProcess(self):
        self.edit.setText(self.edit.text().trimmed())

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.undo()
            ev.accept()
        else:
            super(LabelDialog, self).keyPressEvent(ev)

