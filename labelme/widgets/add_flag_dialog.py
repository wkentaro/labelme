from PyQt5.QtWidgets import QWidget
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
import labelme.utils

class FlagDialog(QtWidgets.QDialog):
    def __init__(
        self,
        text="Enter object label",
        parent=None,
        show_text_field=True,
        fit_to_content=None,
        flags=None,
    ):
        super(FlagDialog, self).__init__(parent)
        self.textBox = QtWidgets.QLineEdit()
        self.textBox.placeholderText = "Name of new flag"
        self.textBox.setValidator(labelme.utils.labelValidator())
        #self.textBox.editingFinished.connect(self.postProcess)
        layout = QtWidgets.QVBoxLayout()
        self.buttonBox = bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            self,
        )
        bb.button(bb.Ok).setIcon(labelme.utils.newIcon("done"))
        bb.button(bb.Cancel).setIcon(labelme.utils.newIcon("undo"))
        bb.accepted.connect(self.save_action)
        bb.rejected.connect(self.cancel)
        layout.addWidget(self.textBox)
        layout.addWidget(bb)
        self.setLayout(layout)
    def save_action(self):
        self.text = self.textBox.text()
        self.close()
    def cancel(self):
        self.close()