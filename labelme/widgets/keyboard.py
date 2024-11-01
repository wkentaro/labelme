from PyQt5.QtWidgets import *
from qtpy import QtWidgets
from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtGui import * 
from labelme.fonts.slavic import SlavicFont

from math import isqrt, ceil

class PushButton(QPushButton):
    SIZE = 45
    def __init__(self, text, parent=None):
        super(PushButton, self).__init__(text, parent)

        self.setText(text)
        self.setFixedSize(QSize(PushButton.SIZE, PushButton.SIZE))

"""
    Окно экранной клавиатуры для вывода всех возможных символов для разметки
"""
class Keyboard(QtWidgets.QDialog): 
    SLOT_SIZE = 60
    def __init__(self, type=None):
        super(Keyboard, self).__init__()

        if type == 'letter':
            self.symbol_list = SlavicFont.LETTERS
        elif type == 'diacritical':
            self.symbol_list = SlavicFont.DIACRITICAL_SIGNS + SlavicFont.TITLA
        else:
            self.symbol_list = SlavicFont.LETTERS + SlavicFont.DIACRITICAL_SIGNS + SlavicFont.TITLA

        # Шиза с размерами клавиатуры
        min_gaps = isqrt(len(self.symbol_list))
        len_sym_list = len(self.symbol_list)
        self.rows = min_gaps + ceil((len_sym_list - min_gaps * min_gaps) / min_gaps)
        self.columns = min_gaps

        possible_width = QApplication.desktop().width() - 40
        possible_height = QApplication.desktop().height() - 100

        grid_width = self.columns * (Keyboard.SLOT_SIZE + 23)
        grid_height = self.rows * (Keyboard.SLOT_SIZE + 23)

        if grid_width < possible_width and grid_height < possible_height:
            self.setMinimumSize(grid_width, grid_height)
        else:
            self.setMinimumSize(possible_width, possible_height)

        self.text_from_keyboard = None
  
        self.layout = QGridLayout()

        i = 0
        for row in range(self.rows): 
            for column in range(self.columns): 
                letter = self.smart_keyboard(i)
                if letter is not None:
                    letter_layout = QtWidgets.QVBoxLayout()
                    letter_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
                    letter_layout.setContentsMargins(0, 0, 0, 0)
                    letter_layout.setSpacing(0)

                    invite_label = QLabel()
                    invite_label.setText(f"{self.get_letter(letter)}")
                    invite_label.setFont(QFont('Arial', 10))
                    letter_layout.addWidget(invite_label, 0, Qt.AlignTop | Qt.AlignHCenter)

                    button = PushButton("")
                    button.setText(f'{letter}')
                    button.setFont(SlavicFont.GetFont(22))
                    button.clicked.connect(self.click)
                    letter_layout.addWidget(button)

                    frame = QFrame()
                    frame.setObjectName("base_frame")
                    frame.setFrameStyle(QFrame.Box | QFrame.Plain)
                    frame.setLineWidth(1)
                    frame.setFixedSize(Keyboard.SLOT_SIZE, Keyboard.SLOT_SIZE + 5)
                    frame.setStyleSheet("#base_frame {border: 1px solid rgb(184, 174, 174); border-radius: 10px;}") 
                    frame.setLayout(letter_layout)

                    self.layout.addWidget(frame, row+1, column)
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
        
    def smart_keyboard(self, i):
        if len(self.symbol_list) > i:
            return self.symbol_list[i]
        else:
            return None
        
    def get_letter(self, letter):
        if letter == ' ':
            return 'Пробел'
        else:
            return letter
        
    def click(self):
        button = QApplication.instance().sender()
        self.text_from_keyboard = button.text()
        self.close()

    def popUp(self):
        self.exec_() 
        return self.text_from_keyboard
        