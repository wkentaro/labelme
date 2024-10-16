from qtpy import QT_VERSION
from qtpy import QtCore
from qtpy import QtWidgets
from PyQt5.QtWidgets import QLabel, QTextEdit, QLineEdit
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import * 

import labelme.utils
from labelme.widgets.keyboard import Keyboard
from labelme.fonts.slavic import SlavicFont

QT5 = QT_VERSION[0] == "5"

"""
    Окно, выдающее ту строку, которую пользователь ввёл со своей и/или с экранной клавиатуры.
    Если пользователь нажал cancel или закрыл окно, то вернётся None
    Если пользователь ввёл всё корректно, то вернётся строка
    Славянская клавиатура добавляет символы в конец вводимой строки 
"""
class LabelLineDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent=None
    ):
        super(LabelLineDialog, self).__init__(parent)
        self.recognised_line = None

        self.setMinimumSize(QSize(600, 100))

        layout = QtWidgets.QVBoxLayout()
        
        invite_label = QLabel()
        invite_label.setText("Разметка строки")
        invite_label.setFont(QFont('Arial', 18))
        layout.addWidget(invite_label, 0, Qt.AlignTop | Qt.AlignHCenter)
        
        layout_slavic_text = QtWidgets.QHBoxLayout()
        invite_text_label = QLabel()
        invite_text_label.setText("Введённая строка:")
        invite_text_label.setFont(QFont('Arial', 8))
        layout_slavic_text.addWidget(invite_text_label, 2)

        self.text_view = QTextEdit()
        self.text_view.setText("")
        self.text_view.setFont(SlavicFont.GetFont(22))
        self.text_view.setReadOnly(True)
        self.text_view.setWordWrapMode(QTextOption.NoWrap)
        self.text_view.setMinimumHeight(75)
        self.text_view.setMaximumHeight(75)
        self.text_view.textChanged.connect(self.cursor_to_right)
        layout_slavic_text.addWidget(self.text_view, 9)

        layout.addLayout(layout_slavic_text)

        layout_enter = QtWidgets.QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Аннотация строки")
        self.edit.textChanged.connect(self.changeLabel)
        layout_enter.addWidget(self.edit, 6)

        keyboard_button = QtWidgets.QPushButton("Славянская клавиатура")
        keyboard_button.clicked.connect(self.get_keyboard)
        layout_enter.addWidget(keyboard_button, 2)
        
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
        if all(letter in SlavicFont.ALL_LETTERS for letter in text):
            self.recognised_line = text
            self.close()
        else:
            messageBox = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning,
                "Ошибка",
                "Введено некорректное значение"
            )
            messageBox.addButton("Ок", QtWidgets.QMessageBox.YesRole)
            messageBox.exec_()
        
    def changeLabel(self):
        self.text_view.setText(self.edit.text())
        
    def cursor_to_right(self):
        cursor = self.text_view.textCursor()     
        cursor.movePosition(QTextCursor.End) 
        self.text_view.setTextCursor(cursor)
        
    def get_keyboard(self):
        letter = Keyboard().popUp()
        if letter is not None:
            self.edit.setText(self.edit.text() + letter)

    def popUp(self):
        self.exec_()
        return self.recognised_line 
