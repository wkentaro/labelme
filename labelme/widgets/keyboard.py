from PyQt5.QtWidgets import *
from qtpy import QtWidgets
from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtGui import * 
from labelme.fonts.slavic import SlavicFont

from math import isqrt, ceil

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
    def __init__(self, type=None):
        super(Keyboard, self).__init__()

        if type == 'letter':
            self.symbol_list = SlavicFont.LETTERS
        elif type == 'diacritical':
            self.symbol_list = SlavicFont.DIACRITICAL_SIGNS
        else:
            self.symbol_list = SlavicFont.LETTERS + SlavicFont.DIACRITICAL_SIGNS

        # Шиза с размерами клавиатуры
        min_gaps = isqrt(len(self.symbol_list))
        len_sym_list = len(self.symbol_list)
        self.rows = min_gaps + ceil((len_sym_list - min_gaps * min_gaps) / min_gaps)
        self.columns = min_gaps

        possible_width = QApplication.desktop().width() - 40
        possible_height = QApplication.desktop().height() - 100
        self.setMaximumSize(possible_width, possible_height)
        grid_width = self.columns * (PushButton.SIZE + 20)
        grid_height = self.rows * (PushButton.SIZE + 40)
        if grid_width < possible_width and grid_height < possible_height:
            self.setFixedSize(grid_width, grid_height)
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
        
    def smart_keyboard(self, i):
        if len(self.symbol_list) > i:
            return self.symbol_list[i]
        else:
            return None
        
    def click(self):
        button = QApplication.instance().sender()
        self.text_from_keyboard = button.text()
        self.close()

    def popUp(self):
        self.exec_() 
        return self.text_from_keyboard
        