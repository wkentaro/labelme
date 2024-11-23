from qtpy import QT_VERSION
from qtpy import QtCore
from qtpy import QtWidgets
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QLineEdit, QTextEdit
from PyQt5.QtCore import Qt, QSize, QEvent
from PyQt5.QtGui import * 
from PyQt5.QtWidgets import *
from labelme.widgets.helper import Helper

import labelme.utils
from labelme.widgets.keyboard import Keyboard
from labelme.fonts.slavic import SlavicFont

QT5 = QT_VERSION[0] == "5"

class Literal:
    def __init__(self, letter, diacritical = None):
        self.letter = letter
        self.diacritical = diacritical

    def to_text(self):
        if self.diacritical is None:
            return self.letter
        else:
            return self.letter + self.diacritical


class LabelLetterDialog(QtWidgets.QDialog):
    """
        Окно, выдающее ту букву, которую пользователь ввёл со своей или с экранной клавиатуры.
        Если пользователь нажал cancel или закрыл окно, то вернётся None
        Если пользователь ввёл всё корректно, то вернётся буква 
    """
    def __init__(
        self,
        helper,
        parent=None,
        old_text=None
    ):
        super(LabelLetterDialog, self).__init__(parent)
        self.recognised_letter = None
        self.helper = helper
        self.workWithKeyboard = False

        self.setMinimumSize(QSize(300, 100))
    
        layout = QtWidgets.QVBoxLayout()

        invite_label = QLabel()
        invite_label.setText("Разметка символа")
        invite_label.setFont(QFont('Arial', 18))
        layout.addWidget(invite_label, 0, Qt.AlignTop | Qt.AlignHCenter)

        self.text_view = QLineEdit()
        if old_text is not None:
            if old_text in SlavicFont.TITLA:
                self.text_view.setText(" " + old_text)
            else:
                self.text_view.setText(old_text)
        self.text_view.setFont(SlavicFont.GetFont(22))
        self.text_view.setReadOnly(True)
        self.text_view.setMaximumHeight(45)
        
        layout.addWidget(self.text_view)
        
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Введите букву")
        if old_text is not None:
            self.edit.setText(old_text)
        self.edit.setMaxLength(2)
        self.edit.textChanged.connect(self.changeLabel)    
        layout.addWidget(self.edit)
        
        layout_enter = QtWidgets.QHBoxLayout()
        keyboard_button = QtWidgets.QPushButton("Славянская клавиатура")
        keyboard_button.clicked.connect(self.get_keyboard_letter)
        layout_enter.addWidget(keyboard_button, 4)

        keyboard_button_2 = QtWidgets.QPushButton("Диакритические знаки")
        keyboard_button_2.clicked.connect(self.get_keyboard_diacritical)
        layout_enter.addWidget(keyboard_button_2, 4)
        
        layout.addLayout(layout_enter)

        # buttons
        self.buttonBox = bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            self,
        )
        bb.button(bb.Ok).setIcon(labelme.utils.newIcon("done"))
        bb.button(bb.Cancel).setIcon(labelme.utils.newIcon("undo"))
        bb.button(bb.Ok).setText("Ок")
        bb.button(bb.Cancel).setText("Отменить")
        if old_text is None:
            bb.button(bb.Ok).setDisabled(True)
        bb.accepted.connect(self.validate_input)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

        self.setLayout(layout)
    
    def changeLabel(self):
        text = self.edit.text()
        symbol_list = SlavicFont.LETTERS + SlavicFont.DIACRITICAL_SIGNS + SlavicFont.TITLA

        if len(text) == 0:
            self.buttonBox.button(self.buttonBox.Ok).setDisabled(True)
        else:
            self.buttonBox.button(self.buttonBox.Ok).setDisabled(False)

        if not all(letter in symbol_list for letter in text):
            self.text_view.setText("")
        else:
            if text in SlavicFont.TITLA:
                self.text_view.setText(" " + text)
            else:
                self.text_view.setText(text)

    def validate_input(self):
        text = self.edit.text()
        if len(text) == 1 and text in SlavicFont.LETTERS + SlavicFont.TITLA:
            self.recognised_letter = Literal(text)
            self.close()
        elif len(text) == 1 and text not in SlavicFont.LETTERS + SlavicFont.TITLA:
            self.getMessageBox("Введённый символ некорректен!") 
        elif len(text) == 2:
            is_correct = self.dia_letter_correct(text)
            if is_correct:
                self.recognised_letter = Literal(text[0], text[1])
                self.close()
            else:
                self.getMessageBox("Некорректная строка с диакритическим знаком!")
        else:
            raise Exception("error in validating text")

    def dia_letter_correct(self, text):
        return text[0] in SlavicFont.LETTERS and text[1] in (SlavicFont.DIACRITICAL_SIGNS + SlavicFont.TITLA)
     
    def getMessageBox(self, text):
        messageBox = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning,
                "Ошибка",
                text
            )
        messageBox.addButton("Ок", QtWidgets.QMessageBox.YesRole)
        messageBox.exec_()
        
    def get_keyboard_letter(self):
        self.workWithKeyboard = True
        letter = Keyboard(self.helper, type='letter').popUp()
        self.workWithKeyboard = False
        if letter is not None:
            self.edit.setText(self.edit.text() + letter)

    def get_keyboard_diacritical(self):
        self.workWithKeyboard = True
        sign = Keyboard(self.helper, type='diacritical').popUp()
        self.workWithKeyboard = False
        if sign is not None:
            self.edit.setText(self.edit.text() + sign)

    def event(self, event):
        if not self.workWithKeyboard and event.type() == QEvent.EnterWhatsThisMode:
            QWhatsThis.leaveWhatsThisMode()
            Helper(self.helper.get_letter_helper()).popUp()
        return QDialog.event(self, event)

    def popUp(self):
        self.exec_()
        return self.recognised_letter
