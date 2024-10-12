from qtpy import QT_VERSION
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import * 

import labelme.utils
from labelme.logger import logger
from labelme.widgets.label_dialog import LabelQLineEdit
from labelme.widgets.keyboard import Keyboard

QT5 = QT_VERSION[0] == "5"

class LabelLetterDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent=None
    ):
        super(LabelLetterDialog, self).__init__(parent)
        self.setMinimumSize(QSize(300, 100))
        self.keyboard = Keyboard()
    
        layout = QtWidgets.QVBoxLayout()

        invite_label = QLabel()
        invite_label.setText("Разметка символа")
        invite_label.setFont(QFont('Arial', 18))
        layout.addWidget(invite_label, 0, Qt.AlignTop | Qt.AlignHCenter)

        layout_enter = QtWidgets.QHBoxLayout()
        self.edit = LabelQLineEdit()
        self.edit.setPlaceholderText("Введите букву")
        layout_enter.addWidget(self.edit, 4)

        self.keyboard_button = QtWidgets.QPushButton("Славянская клавиатура")
        self.keyboard_button.clicked.connect(self.get_keyboard)
        layout_enter.addWidget(self.keyboard_button, 4)
        
        layout.addLayout(layout_enter)

        # buttons
        self.buttonBox = bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            self,
        )
        bb.button(bb.Ok).setIcon(labelme.utils.newIcon("done"))
        bb.button(bb.Cancel).setIcon(labelme.utils.newIcon("undo"))
        layout.addWidget(bb)

        self.setLayout(layout)
    
    def get_keyboard(self):
        self.keyboard.popUp()

    def popUp(self):
        self.exec_()
        return None, None
