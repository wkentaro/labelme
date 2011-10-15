
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from lib import newButton, labelValidator

BB = QDialogButtonBox

# FIXME:
# - Use the validator when accepting the dialog.

class LabelDialog(QDialog):
    OK, UNDO, DELETE = range(3)

    def __init__(self, text='', parent=None):
        super(LabelDialog, self).__init__(parent)
        self.action = self.OK
        self.edit = QLineEdit()
        self.edit.setText(text)
        self.edit.setValidator(labelValidator())
        self.edit.editingFinished.connect(self.postProcess)
        layout = QHBoxLayout()
        layout.addWidget(self.edit)
        delete = newButton('Delete', icon='delete', slot=self.delete)
        undo = newButton('Undo close', icon='undo', slot=self.undo)
        bb = BB(Qt.Vertical, self)
        bb.addButton(BB.Ok)
        bb.addButton(undo, BB.RejectRole)
        bb.addButton(delete, BB.RejectRole)
        bb.accepted.connect(self.validate)
        layout.addWidget(bb)
        self.setLayout(layout)

    def undo(self):
        self.action = self.UNDO
        self.reject()

    def delete(self):
        self.action = self.DELETE
        self.reject()

    def text(self):
        return self.edit.text()

    def popUp(self, position):
        # It actually works without moving...
        #self.move(position)
        self.edit.setText(u"Enter label")
        self.edit.setSelection(0, len(self.text()))
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

