
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from lib import newButton

BB = QDialogButtonBox

class LabelDialog(QDialog):
    OK, UNDO, DELETE = range(3)

    def __init__(self, text='', parent=None):
        super(LabelDialog, self).__init__(parent)
        self.action = self.OK
        self.edit = QLineEdit()
        self.edit.setText(text)
        layout = QHBoxLayout()
        layout.addWidget(self.edit)
        delete = newButton('Delete', icon='delete', slot=self.delete)
        undo = newButton('Undo close', icon='undo', slot=self.undo)
        bb = BB(Qt.Vertical, self)
        bb.addButton(BB.Ok)
        bb.addButton(undo, BB.RejectRole)
        bb.addButton(delete, BB.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.setLayout(layout)

    def undo(self):
        self.action = self.UNDO

    def delete(self):
        self.action = self.DELETE

    def text(self):
        return self.edit.text()

    def popUp(self, position):
        # It actually works without moving...
        #self.move(position)
        self.edit.setText(u"Enter label")
        self.edit.setSelection(0, len(self.text()))
        self.edit.setFocus(Qt.PopupFocusReason)
        return self.OK if self.exec_() else self.action

