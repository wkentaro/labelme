#!/usr/bin/env python
# -*- coding: utf8 -*-

import sys

from PyQt4.QtGui import *
from PyQt4.QtCore import *


__appname__ = 'labelme'


### Utility functions and classes.

def action(parent, text, slot=None, shortcut=None, icon=None,
           tip=None, checkable=False):
    """Create a new action and assign callbacks, shortcuts, etc."""
    a = QAction(text, parent)
    if icon is not None:
        a.setIcon(QIcon(u':/%s' % icon))
    if shortcut is not None:
        a.setShortcut(shortcut)
    if tip is not None:
        a.setToolTip(tip)
        a.setStatusTip(tip)
    if slot is not None:
        a.triggered.connect(slot)
    if checkable:
        a.setCheckable(True)
    return a

def add_actions(widget, actions):
    for action in actions:
        if action is None:
            widget.addSeparator()
        else:
            widget.addAction(action)

class WindowMixin(object):
    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            add_actions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = QToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        #toolbar.setOrientation(Qt.Vertical)
        toolbar.setContentsMargins(0,0,0,0)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        toolbar.layout().setContentsMargins(0,0,0,0)
        if actions:
            add_actions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


class MainWindow(QMainWindow, WindowMixin):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        self.setContentsMargins(0, 0, 0, 0)

        # Main widgets.
        self.label = QLineEdit(u'Hello world, مرحبا ، العالم, Γεια σου κόσμε!')
        self.dock = QDockWidget(u'Label', parent=self)
        self.dock.setWidget(self.label)

        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock)
        self.setCentralWidget(QWidget())

        # Actions
        quit = action(self, '&Quit', self.close, 'Ctrl+Q', u'Exit application')
        labl = self.dock.toggleViewAction()
        labl.setShortcut('Ctrl+L')

        add_actions(self.menu('&File'), (labl, None, quit))
        add_actions(self.toolbar('Tools'), (labl, None, quit,))

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()


def main(argv):
    """Standard boilerplate Qt application code."""
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    win = MainWindow()
    win.show()
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main(sys.argv))

