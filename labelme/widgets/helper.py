from PyQt5.QtWidgets import *
from qtpy import QtWidgets
from PyQt5.QtGui import * 
from qtpy import QtCore

import labelme.widgets.helper_text.help

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
            # Прочитываем файлы из ресурсов
            self.keyboard = self.__read_resource_file(":/keyboard.txt")
            self.letter = self.__read_resource_file(":/letter.txt")
            self.line = self.__read_resource_file(":/line.txt")
            self.main = self.__read_resource_file(":/main.txt")
        except:
            raise Exception("error in helper files loading")
        
    def __read_resource_file(self, path):
        f = QtCore.QFile(path)
        if f.open(QtCore.QIODevice.ReadOnly | QtCore.QFile.Text):
            text = QtCore.QTextStream(f)
            text.setCodec("UTF-8")
        result = ""
        while not text.atEnd():
            result += text.readLine()
        f.close()
        return result
        
    def get_letter_helper(self):
        return self.letter
    
    def get_keyboard_helper(self):
        return self.keyboard
    
    def get_line_helper(self):
        return self.line 
    
    def get_main_helper(self):
        return self.main
