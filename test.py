#!/usr/bin/env python
# -*- coding: utf8 -*-

import sys

from PyQt4.QtGui import *
from PyQt4.QtCore import *

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle("test")

        quit = QAction("&Quit", self)
        quit.triggered.connect(self.close)

        menu = self.menuBar().addMenu('&File')
        menu.addAction(quit)

        self.notepad = QTabWidget()
        tabs = [("hello", QWidget(), "test")]
        for i, (name, widget, title) in enumerate(tabs):
            self.notepad.addTab(widget, title)

        self.setCentralWidget(self.notepad)
        self.statusBar().show()


def main(argv):
    app = QApplication(argv)
    app.setApplicationName("test")
    win = MainWindow()
    win.show()
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main(sys.argv))

