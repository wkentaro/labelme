from qtpy import QT_VERSION
from qtpy import QtCore
from qtpy import QtWidgets
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import * 

import labelme.utils
from labelme.widgets.keyboard import Keyboard
from labelme.fonts.slavic import SlavicFont

QT5 = QT_VERSION[0] == "5"

"""
    Окно, выдающее ту букву, которую пользователь ввёл со своей или с экранной клавиатуры.
    Если пользователь нажал cancel или закрыл окно, то вернётся None
    Если пользователь ввёл всё корректно, то вернётся буква 
"""
class LabelLetterDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent=None
    ):
        super(LabelLetterDialog, self).__init__(parent)
        self.recognised_letter = None

        self.setMinimumSize(QSize(300, 100))
    
        layout = QtWidgets.QVBoxLayout()

        invite_label = QLabel()
        invite_label.setText("Разметка символа")
        invite_label.setFont(QFont('Arial', 18))
        layout.addWidget(invite_label, 0, Qt.AlignTop | Qt.AlignHCenter)

        layout_enter = QtWidgets.QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Введите букву")
        layout_enter.addWidget(self.edit, 4)

        keyboard_button = QtWidgets.QPushButton("Славянская клавиатура")
        keyboard_button.clicked.connect(self.get_keyboard)
        layout_enter.addWidget(keyboard_button, 4)
        
        layout.addLayout(layout_enter)

        # buttons
        self.buttonBox = bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            self,
        )
        bb.button(bb.Ok).setIcon(labelme.utils.newIcon("done"))
        bb.button(bb.Cancel).setIcon(labelme.utils.newIcon("undo"))
        bb.accepted.connect(self.validate_input)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

        self.setLayout(layout)
    
    def validate_input(self):
        text = self.edit.text()
        if len(text) == 1 and text in SlavicFont.ALL_LETTERS:
            self.recognised_letter = text
            self.close()
        else:
            messageBox = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning,
                "Ошибка",
                "Введено некорректное значение"
            )
            messageBox.addButton("Ок", QtWidgets.QMessageBox.YesRole)
            messageBox.exec_()

    def get_keyboard(self):
        letter = Keyboard().popUp()
        if letter is not None:
            self.edit.setText(letter)

    def popUp(self):
        self.exec_()
        return self.recognised_letter
