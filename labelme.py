#!/usr/bin/env python
# -*- coding: utf8 -*-

import re
import sys

from collections import defaultdict

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
        self.dock.setObjectName(u'Label')
        self.dock.setWidget(self.label)

        self.imageWidget = QLabel()
        self.imageWidget.setAlignment(Qt.AlignCenter)
        self.imageWidget.setContextMenuPolicy(Qt.ActionsContextMenu)

        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock)
        self.setCentralWidget(self.imageWidget)

        # Actions
        quit = action(self, '&Quit', self.close, 'Ctrl+Q', u'Exit application')
        labl = self.dock.toggleViewAction()
        labl.setShortcut('Ctrl+L')

        add_actions(self.menu('&File'), (labl, None, quit))
        add_actions(self.toolbar('Tools'), (labl, None, quit,))

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.filename = ''
        self.recent_files = []

        # TODO: Could be completely declarative.
        # Restore application settings.
        types = {
            'filename': QString,
            'recent-files': QStringList,
            'window/size': QSize,
            'window/position': QPoint,
            'window/geometry': QByteArray,
            # Docks and toolbars:
            'window/state': QByteArray,
        }
        self.settings = settings = Settings(types)
        self.recent_files = settings['recent-files']
        size = settings.get('window/size', QSize(600, 500))
        position = settings.get('window/position', QPoint(0, 0))
        self.resize(size)
        self.move(position)
        # or simply:
        #self.restoreGeometry(settings['window/geometry']
        self.restoreState(settings['window/state'])

        # The file menu has default dynamically generated entries.
        self.updateFileMenu()
        # Since loading the file may take some time, make sure it runs in the background.
        self.queueEvent(self.loadFile)

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def loadFile(self, filename=None):
        """Load the specified file, or the last opened file if None."""
        if filename is None:
            filename = self.settings['filename']
        # FIXME: Load the actual file here.
        if QFile.exists(filename):
            # Load image
            image = QImage(filename)
            if image.isNull():
                message = "Failed to read %s" % filename
            else:
                message = "Loaded %s" % os.path.basename(unicode(filename))
                self.showImage()
                self.image = image
                self.filename = filename
            self.statusBar().showMessage(message)

    def showImage(self):
        if self.image.isNull():
            return
        self.imageWidget.setPixmap(QPixmap.fromImage(self.image))

    def closeEvent(self, event):
        # TODO: Make sure changes are saved.
        s = self.settings
        s['filename'] = self.filename if self.filename else QString()
        s['window/size'] = self.size()
        s['window/position'] = self.pos()
        s['window/state'] = self.saveState()
        #s['window/geometry'] = self.saveGeometry()

    def updateFileMenu(self):
        """Populate menu with recent files."""


class Settings(object):
    """Convenience dict-like wrapper around QSettings."""
    def __init__(self, types=None):
        self.data = QSettings()
        self.types = defaultdict(lambda: QVariant, types if types else {})

    def __setitem__(self, key, value):
        t = self.types[key]
        self.data.setValue(key,
                t(value) if not isinstance(value, t) else value)

    def __getitem__(self, key):
        return self._cast(key, self.data.value(key))

    def get(self, key, default=None):
        return self._cast(key, self.data.value(key, default))

    def _cast(self, key, value):
        # XXX: Very nasty way of converting types to QVariant methods :P
        t = self.types[key]
        if t != QVariant:
            method = getattr(QVariant, re.sub('^Q', 'to', t.__name__, count=1))
            return method(value)
        return value




def main(argv):
    """Standard boilerplate Qt application code."""
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    win = MainWindow()
    win.show()
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main(sys.argv))

