from PyQt5.QtWidgets import *
from qtpy import QtWidgets
from PyQt5.QtCore import QSize
from labelme.fonts.slavic import SlavicFont

class PushButton(QPushButton):
    SIZE = 40
    def __init__(self, text, parent=None):
        super(PushButton, self).__init__(text, parent)

        self.setText(text)
        self.setMinimumSize(QSize(PushButton.SIZE, PushButton.SIZE))
        self.setMaximumSize(QSize(PushButton.SIZE, PushButton.SIZE))

class Keyboard(QtWidgets.QDialog): 
    def __init__(self):
        super(Keyboard, self).__init__()

        self.rows = 16
        self.columns = 16

        self.layout = QGridLayout()

        i = 0
        for row in range(self.rows): 
            for column in range(self.columns): 
                    button = PushButton("")
                    button.setText(f'{chr(i)}')
                    button.setFont(SlavicFont.GetFont(20))
                    self.layout.addWidget(button, row+1, column)
                    i += 1
        
        self.setLayout(self.layout)


    def popUp(self):
        self.exec_()