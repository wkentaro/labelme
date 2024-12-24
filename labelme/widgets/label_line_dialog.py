from qtpy import QT_VERSION
from qtpy import QtCore
from qtpy import QtWidgets
from PyQt5.QtWidgets import QLabel, QTextEdit, QLineEdit
from PyQt5.QtCore import Qt, QSize, QEvent
from PyQt5.QtGui import * 
from PyQt5.QtWidgets import *
from labelme.widgets.helper import Helper

import labelme.utils
from labelme.widgets.keyboard import Keyboard
from labelme.fonts.slavic import SlavicFont
from labelme.widgets.label_letter_dialog import Literal

QT5 = QT_VERSION[0] == "5"


class LabelLineDialog(QtWidgets.QDialog):
    """
        Окно, выдающее ту строку, которую пользователь ввёл со своей и/или с экранной клавиатуры.
        Если пользователь нажал cancel или закрыл окно, то вернётся None
        Если пользователь ввёл всё корректно, то вернётся строка
        Славянская клавиатура добавляет символы в конец вводимой строки 
    """
    def __init__(
        self,
        helper,
        parent=None,
        old_text=None
    ):
        super(LabelLineDialog, self).__init__(parent)
        self.recognised_line = None
        self.helper = helper
        self.workWithKeyboard = False

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
        if old_text is not None:
            self.text_view.setText(old_text)
        self.text_view.setFont(SlavicFont.GetFont(22))
        self.text_view.setReadOnly(True)
        self.text_view.setWordWrapMode(QTextOption.NoWrap)
        self.text_view.setFixedHeight(65)
        self.text_view.textChanged.connect(self.cursor_to_right)
        layout_slavic_text.addWidget(self.text_view, 9)

        layout.addLayout(layout_slavic_text)

        layout_enter = QtWidgets.QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Аннотация строки")
        if old_text is not None:
            self.edit.setText(old_text)
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
        bb.button(bb.Ok).setText("Ок")
        bb.button(bb.Cancel).setText("Отменить")
        bb.accepted.connect(self.validate_input)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

        self.setLayout(layout)

    def validate_input(self):
        text = self.edit.text()
        symbol_list = SlavicFont.LETTERS + SlavicFont.DIACRITICAL_SIGNS + SlavicFont.TITLA
        if text == "":
            self.recognised_line = Literal(text)
            self.close()
            return
        if not all(letter in symbol_list for letter in text):
            self.getMessageBox("Введён некорректный символ!")
        elif text[0] in SlavicFont.DIACRITICAL_SIGNS + SlavicFont.TITLA:
            self.getMessageBox("Диакритический знак или титло не может быть в начале строки!") 
        else:
            all_upper = SlavicFont.DIACRITICAL_SIGNS + SlavicFont.TITLA
            for i in range(len(text) - 1):
                if text[i] in all_upper and text[i + 1] in all_upper:
                    self.getMessageBox("В строке не могут подряд идти 2 диакритических знака!")
                    return
            self.recognised_line = Literal(text)
            self.close()

    def getMessageBox(self, text):
        messageBox = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning,
                "Ошибка",
                text
            )
        messageBox.addButton("Ок", QtWidgets.QMessageBox.YesRole)
        messageBox.exec_()
        
    def changeLabel(self):
        text = self.edit.text()
        symbol_list = SlavicFont.LETTERS + SlavicFont.DIACRITICAL_SIGNS + SlavicFont.TITLA
        
        if not all(letter in symbol_list for letter in text):
            self.text_view.setText("")
        else:
            self.text_view.setText(text)
        
    def cursor_to_right(self):
        cursor = self.text_view.textCursor()     
        cursor.movePosition(QTextCursor.End) 
        self.text_view.setTextCursor(cursor)
        
    def get_keyboard(self):
        self.workWithKeyboard = True
        letter = Keyboard(self.helper).popUp()
        self.workWithKeyboard = False
        if letter is not None:
            self.edit.setText(self.edit.text() + letter)

    def event(self, event):
        if not self.workWithKeyboard and event.type() == QEvent.EnterWhatsThisMode:
            QWhatsThis.leaveWhatsThisMode()
            Helper(self.helper.get_line_helper()).popUp()
        return QDialog.event(self, event)

    def popUp(self):
        self.exec_()
        return self.recognised_line 
