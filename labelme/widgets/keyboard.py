from PyQt5.QtWidgets import *
from qtpy import QtWidgets
from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtGui import * 
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
        
        self.setMinimumSize(QApplication.desktop().width() - 40, QApplication.desktop().height() - 100)

        self.text_from_keyboard = None

        self.rows = 16
        self.columns = 16
        
        self.layout = QGridLayout()

        # for i in range(self.columns):
        #     self.layout.setColumnMinimumWidth(i, 50)

        # for i in range(3, self.rows):
        #     self.layout.setRowMinimumHeight(i, 60)

        i = 0
        for row in range(self.rows): 
            for column in range(self.columns): 
                letter = self.smart_keyboard(i)
                if letter is not None:
                    letter_layout = QtWidgets.QVBoxLayout()

                    invite_label = QLabel()
                    invite_label.setText(f"{letter}")
                    invite_label.setFont(QFont('Arial', 10))
                    letter_layout.addWidget(invite_label, 0, Qt.AlignTop | Qt.AlignHCenter)

                    button = PushButton("")
                    button.setText(f'{letter}')
                    button.setFont(SlavicFont.GetFont(22))
                    button.clicked.connect(self.click)
                    letter_layout.addWidget(button)

                    self.layout.addLayout(letter_layout, row+1, column)
                i += 1

        layoutH = QHBoxLayout()  
        layoutV = QVBoxLayout()        
        scroll = QScrollArea()  
        self.widget = QWidget() 
        layoutH.addWidget(scroll)
        self.widget.setLayout(self.layout)
        scroll.setWidget(self.widget)
        scroll.setWidgetResizable(True) 
        layoutV.addLayout(layoutH)
        self.setLayout(layoutV)

    def smart_keyboard(self, x : int):
        if x >= 32 and x <= len(SlavicFont.ALL_LETTERS) + 31:
            return SlavicFont.ALL_LETTERS[x - 32]
        else:
            return None
        
    def click(self):
        button = QApplication.instance().sender()
        self.text_from_keyboard = button.text()
        self.close()

    def popUp(self):
        self.exec_() 
        return self.text_from_keyboard
        