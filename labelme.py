#!/usr/bin/env python
# -*- coding: utf8 -*-

import os.path
import re
import sys

from functools import partial
from collections import defaultdict

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from canvas import Canvas
from zoomwidget import ZoomWidget

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
    def __init__(self, filename=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        self.setContentsMargins(0, 0, 0, 0)

        # Main widgets.
        self.label = QLineEdit(u'Hello world, مرحبا ، العالم, Γεια σου κόσμε!')
        self.dock = QDockWidget(u'Label', parent=self)
        self.dock.setObjectName(u'Label')
        self.dock.setWidget(self.label)
        self.zoom_widget = ZoomWidget()
        #self.dock.setFeatures(QDockWidget.DockWidgetMovable|QDockWidget.DockWidgetFloatable)

        self.canvas = Canvas()
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setContextMenuPolicy(Qt.ActionsContextMenu)

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock)

        # Actions
        quit = action(self, '&Quit', self.close, 'Ctrl+Q', u'Exit application')
        open = action(self, '&Open', self.openFile, 'Ctrl+O', u'Open file')
        color = action(self, '&Color', self.chooseColor, 'Ctrl+C', u'Choose line color')
        labl = self.dock.toggleViewAction()
        labl.setShortcut('Ctrl+L')

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoom_widget)
        fit_window = action(self, '&Fit Window', self.setFitWindow,
                'Ctrl+F', u'Fit image to window', checkable=True)

        self.menus = struct(
                file=self.menu('&File'),
                edit=self.menu('&Image'),
                view=self.menu('&View'))
        add_actions(self.menus.file, (open, quit))
        add_actions(self.menus.edit, (color, fit_window))
        add_actions(self.menus.view, (labl,))

        self.tools = self.toolbar('Tools')
        add_actions(self.tools, (open, color, None, zoom, fit_window, None, quit))


        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.filename = filename
        self.recent_files = []
        self.color = None
        self.zoom_level = 100
        self.fit_window = False

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
        self.color = QColor(settings.get('line/color', QColor(0, 255, 0, 128)))

        # The file menu has default dynamically generated entries.
        self.updateFileMenu()
        # Since loading the file may take some time, make sure it runs in the background.
        self.queueEvent(partial(self.loadFile, self.filename))

        # Callbacks:
        self.zoom_widget.valueChanged.connect(self.showImage)


    ## Callback functions:
    def setFitWindow(self, value=True):
        self.zoom_widget.setEnabled(not value)
        self.fit_window = value
        self.showImage()

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
                self.image = image
                self.filename = filename
                self.showImage()
            self.statusBar().showMessage(message)

    def resizeEvent(self, event):
        if self.fit_window and self.canvas and not self.image.isNull():
            self.showImage()
        super(MainWindow, self).resizeEvent(event)

    def showImage(self):
        if self.image.isNull():
            return
        size = self.imageSize()
        self.canvas.setPixmap(QPixmap.fromImage(self.image.scaled(
                size, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        self.canvas.show()

    def imageSize(self):
        """Calculate the size of the image based on current settings."""
        if self.fit_window:
            width, height = self.centralWidget().width()-2, self.centralWidget().height()-2
        else: # Follow zoom:
            s = self.zoom_widget.value() / 100.0
            width, height = s * self.image.width(), s * self.image.height()
        return QSize(width, height)

    def closeEvent(self, event):
        # TODO: Make sure changes are saved.
        s = self.settings
        s['filename'] = self.filename if self.filename else QString()
        s['window/size'] = self.size()
        s['window/position'] = self.pos()
        s['window/state'] = self.saveState()
        s['line/color'] = self.color
        #s['window/geometry'] = self.saveGeometry()

    def updateFileMenu(self):
        """Populate menu with recent files."""

    ## Dialogs.
    def openFile(self):
        if not self.check():
            return
        path = os.path.dirname(unicode(self.filename))\
                if self.filename else '.'
        formats = ['*.%s' % unicode(fmt).lower()\
                for fmt in QImageReader.supportedImageFormats()]
        filename = unicode(QFileDialog.getOpenFileName(self,
            '%s - Choose Image', path, 'Image files (%s)' % ' '.join(formats)))
        if filename:
            self.loadFile(filename)

    def check(self):
        # TODO: Prompt user to save labels etc.
        return True

    def chooseColor(self):
        self.color = QColorDialog.getColor(self.color, self,
                u'Choose line color', QColorDialog.ShowAlphaChannel)


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


class struct(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def main(argv):
    """Standard boilerplate Qt application code."""
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    win = MainWindow(argv[1] if len(argv) == 2 else None)
    win.show()
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main(sys.argv))

