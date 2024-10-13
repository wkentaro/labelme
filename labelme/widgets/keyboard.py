from PyQt5.QtWidgets import *
from qtpy import QtWidgets
from PyQt5.QtCore import QSize
from labelme.fonts.slavic import SlavicFont

class PushButton(QPushButton):
    SIZE = 50
    def __init__(self, text, parent=None):
        super(PushButton, self).__init__(text, parent)

        self.setText(text)
        self.setMinimumSize(QSize(PushButton.SIZE, PushButton.SIZE))
        self.setMaximumSize(QSize(PushButton.SIZE, PushButton.SIZE))

"""
    Окно экранной клавиатуры для вывода всех возможных символов для разметки
"""
class Keyboard(QtWidgets.QDialog): 
    def __init__(self):
        super(Keyboard, self).__init__()

        self.text_from_keyboard = None

        self.rows = 16
        self.columns = 16

        self.layout = QGridLayout()

        i = 0
        for row in range(self.rows): 
            for column in range(self.columns): 
                letter = self.smart_keyboard(i)
                if letter is not None:
                    button = PushButton("")
                    button.setText(f'{letter}')
                    button.setFont(SlavicFont.GetFont(22))
                    button.clicked.connect(self.click)
                    self.layout.addWidget(button, row+1, column)
                i += 1
        
        self.setLayout(self.layout)

    def smart_keyboard(self, x : int):
        if x >= 0 and x <= 31:
            return None
        elif x >= 32 and x <= 255:
            return SlavicFont.ALL_LETTERS[x - 32]
        else:
            raise Exception("fatal in smart_keyboard: wrong letter to encode")
        
    def click(self):
        button = QApplication.instance().sender()
        self.text_from_keyboard = button.text()
        self.close()

    def popUp(self):
        self.exec_()
        return self.text_from_keyboard
        