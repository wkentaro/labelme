from PyQt5.QtWidgets import *
from qtpy import QtWidgets
from PyQt5.QtGui import * 
from qtpy import QtCore

class Helper(QtWidgets.QDialog):
    def __init__(self, text):
        super(Helper, self).__init__(None, QtCore.Qt.WindowSystemMenuHint | QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowCloseButtonHint)

        self.label = QLabel(text, self)
        self.label.setMaximumWidth(500)
        self.label.setWordWrap(True) 

        layout = QVBoxLayout(self)
        layout.addWidget(self.label, stretch=1)

        self.setLayout(layout)

    def popUp(self):
        self.exec_() 


class HelperString:
    def __init__(self):
        try:
            with open("labelme\\widgets\\hepler_text\\keyboard.txt", 'r', encoding='utf-8') as keyboard_file:
                self.keyboard = keyboard_file.read()
            with open("labelme\\widgets\\hepler_text\\letter.txt", 'r', encoding='utf-8') as letter_file:
                self.letter = letter_file.read()
            with open("labelme\\widgets\\hepler_text\\line.txt", 'r', encoding='utf-8') as line_file:
                self.line = line_file.read()
            with open("labelme\\widgets\\hepler_text\\main.txt", 'r', encoding='utf-8') as main_file:
                self.main = main_file.read()
        except:
            raise Exception("error in helper files loading")
        
    def get_letter_helper(self):
        return self.letter
    
    def get_keyboard_helper(self):
        return self.keyboard
    
    def get_line_helper(self):
        return self.line 
    
    def get_main_helper(self):
        return self.main
