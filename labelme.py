#!/usr/bin/env python
# -*- coding: utf8 -*-

import os.path
import re
import sys

from functools import partial
from collections import defaultdict

from PyQt4.QtGui import *
from PyQt4.QtCore import *

import resources

from lib import newAction, addActions, labelValidator
from shape import Shape
from canvas import Canvas
from zoomWidget import ZoomWidget
from labelDialog import LabelDialog
from labelFile import LabelFile


__appname__ = 'labelme'

# FIXME
# - [low] Label validation/postprocessing breaks with TAB.
# - Disable context menu entries depending on context.

# TODO:
# - Add a new column in list widget with checkbox to show/hide shape.
# - Make sure the `save' action is disabled when no labels are
#   present in the image, e.g. when all of them are deleted.
# - [easy] Add button to Hide/Show all labels.
# - Zoom is too "steppy".


### Utility functions and classes.

class WindowMixin(object):
    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = QToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        #toolbar.setOrientation(Qt.Vertical)
        toolbar.setContentsMargins(0,0,0,0)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        toolbar.layout().setContentsMargins(0,0,0,0)
        if actions:
            addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


class MainWindow(QMainWindow, WindowMixin):
    def __init__(self, filename=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        self.setContentsMargins(0, 0, 0, 0)

        # Main widgets.
        self.label = LabelDialog(parent=self)
        self.labels = {}
        self.items = {}
        self.highlighted = None
        self.labelList = QListWidget()
        self.dock = QDockWidget(u'Labels', self)
        self.dock.setObjectName(u'Labels')
        self.dock.setWidget(self.labelList)
        self.zoom_widget = ZoomWidget()

        self.labelList.setItemDelegate(LabelDelegate())
        self.labelList.itemActivated.connect(self.highlightLabel)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)

        self.canvas = Canvas()
        #self.canvas.setAlignment(Qt.AlignCenter)

        self.canvas.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.canvas.zoomRequest.connect(self.zoomRequest)

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
            }
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        # Actions
        action = partial(newAction, self)
        quit = action('&Quit', self.close,
                'Ctrl+Q', 'quit', u'Exit application')
        open = action('&Open', self.openFile,
                'Ctrl+O', 'open', u'Open file')
        save = action('&Save', self.saveFile,
                'Ctrl+S', 'save', u'Save file')
        color = action('&Color', self.chooseColor,
                'Ctrl+C', 'color', u'Choose line color')
        label = action('&New Item', self.newLabel,
                'Ctrl+N', 'new', u'Add new label')
        copy = action('&Copy', self.copySelectedShape,
                'Ctrl+C', 'copy', u'Copy')
        delete = action('&Delete', self.deleteSelectedShape,
                'Ctrl+D', 'delete', u'Delete')
        hide = action('&Hide labels', self.hideLabelsToggle,
                'Ctrl+H', 'hide', u'Hide background labels when drawing',
                checkable=True)

        self.canvas.setContextMenuPolicy( Qt.CustomContextMenu )
        self.canvas.customContextMenuRequested.connect(self.popContextMenu)

        # Popup Menu
        self.popMenu = QMenu(self )
        self.popMenu.addAction( label )
        self.popMenu.addAction(copy)
        self.popMenu.addAction( delete )

        labels = self.dock.toggleViewAction()
        labels.setShortcut('Ctrl+L')

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoom_widget)

        # Store actions for further handling.
        self.actions = struct(save=save, open=open, color=color,
                label=label, delete=delete, zoom=zoom)
        save.setEnabled(False)

        fit_window = action('&Fit Window', self.setFitWindow,
                'Ctrl+F', 'fit',  u'Fit image to window', checkable=True)

        self.menus = struct(
                file=self.menu('&File'),
                edit=self.menu('&Image'),
                view=self.menu('&View'))
        addActions(self.menus.file, (open, save, quit))
        addActions(self.menus.edit, (label, color, fit_window))

        addActions(self.menus.view, (labels,))

        self.tools = self.toolbar('Tools')
        addActions(self.tools, (open, save, color, None, label, delete, hide, None,
            zoom, fit_window, None, quit))


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
        self.zoom_widget.editingFinished.connect(self.paintCanvas)

    def popContextMenu(self, point):
        self.popMenu.exec_(self.canvas.mapToGlobal(point))

    def addLabel(self, shape):
        item = QListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
        item.setCheckState(Qt.Checked)
        self.labels[item] = shape
        self.items[shape] = item
        self.labelList.addItem(item)

    def remLabel(self, shape):
        item = self.items.get(shape, None)
        self.labelList.takeItem(self.labelList.row(item))

    def loadLabels(self, shapes):
        s = []
        for label, points in shapes:
            shape = Shape(label=label)
            shape.fill = True
            for x, y in points:
                shape.addPoint(QPointF(x, y))
            s.append(shape)
            self.addLabel(shape)
        self.canvas.loadShapes(s)

    def saveLabels(self, filename):
        lf = LabelFile()
        shapes = [(unicode(shape.label), [(p.x(), p.y()) for p in shape.points])\
                for shape in self.canvas.shapes]
        lf.save(filename, shapes, unicode(self.filename), self.imageData)

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())

    def highlightLabel(self, item):
        if self.highlighted:
            self.highlighted.fill_color = Shape.fill_color
        shape = self.labels[item]
        shape.fill_color = inverted(Shape.fill_color)
        self.highlighted = shape
        self.canvas.repaint()

    def labelItemChanged(self, item):
        shape = self.labels[item]
        label = unicode(item.text())
        if label != shape.label:
            self.stateChanged()
            shape.label = unicode(item.text())
        else: # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    def stateChanged(self):
        self.actions.save.setEnabled(True)

    ## Callback functions:
    def newShape(self, position):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        action = self.label.popUp(position)
        if action == self.label.OK:
            self.addLabel(self.canvas.setLastLabel(self.label.text()))
            # Enable the save action.
            self.actions.save.setEnabled(True)
        elif action == self.label.UNDO:
            self.canvas.undoLastLine()
        elif action == self.label.DELETE:
            self.canvas.deleteLastShape()
        else:
            assert False, "unknown label action"

    def scrollRequest(self, delta, orientation):
        units = - delta / (8 * 15)
        bar = self.scrollBars[orientation]
        bar.setValue(bar.value() + bar.singleStep() * units)

    def zoomRequest(self, delta):
        if not self.fit_window:
            units = delta / (8 * 15)
            scale = 10
            self.zoom_widget.setValue(self.zoom_widget.value() + scale * units)
            self.zoom_widget.editingFinished.emit()

    def setFitWindow(self, value=True):
        self.zoom_widget.setEnabled(not value)
        self.fit_window = value
        self.paintCanvas()

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def hideLabelsToggle(self, value):
        self.canvas.hideBackroundShapes(value)

    def loadFile(self, filename=None):
        """Load the specified file, or the last opened file if None."""
        if filename is None:
            filename = self.settings['filename']
        filename = unicode(filename)
        if QFile.exists(filename):
            if LabelFile.isLabelFile(filename):
                # TODO: Error handling.
                lf = LabelFile()
                lf.load(filename)
                self.labelFile = lf
                self.imageData = lf.imageData
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.imageData = read(filename, None)
                self.labelFile = None
            image = QImage.fromData(self.imageData)
            if image.isNull():
                message = "Failed to read %s" % filename
            else:
                message = "Loaded %s" % os.path.basename(unicode(filename))
                self.image = image
                self.filename = filename
                self.labels = {}
                self.labelList.clear()
                self.canvas.loadPixmap(QPixmap.fromImage(image))
                if self.labelFile:
                    self.loadLabels(self.labelFile.shapes)
            self.statusBar().showMessage(message)

    def resizeEvent(self, event):
        if self.fit_window and self.canvas and not self.image.isNull():
            self.paintCanvas()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = self.fitSize() if self.fit_window\
                            else 0.01 * self.zoom_widget.value()
        self.canvas.adjustSize()
        self.canvas.repaint()

    def fitSize(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        e = 2.0 # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1/ h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2


    def closeEvent(self, event):
        # TODO: Make sure changes are saved.
        s = self.settings
        s['filename'] = self.filename if self.filename else QString()
        s['window/size'] = self.size()
        s['window/position'] = self.pos()
        s['window/state'] = self.saveState()
        s['line/color'] = self.color
        # ask the use for where to save the labels
       

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
        filters = 'Image files (%s)\nLabel files (*%s)'\
                % (' '.join(formats), LabelFile.suffix)
        filename = unicode(QFileDialog.getOpenFileName(self,
            '%s - Choose Image', path, filters))
        if filename:
            self.loadFile(filename)

    def saveFile(self):
        assert not self.image.isNull(), "cannot save empty image"
        # XXX: What if user wants to remove label file?
        assert self.labels, "cannot save empty labels"
        path = os.path.dirname(unicode(self.filename))\
                if self.filename else '.'
        formats = ['*%s' % LabelFile.suffix]
        filename = unicode(QFileDialog.getSaveFileName(self,
            '%s - Choose File', path, 'Label files (%s)' % ''.join(formats)))
        if filename:
            self.saveLabels(filename)

    def check(self):
        # TODO: Prompt user to save labels etc.
        return True

    def chooseColor(self):
        self.color = QColorDialog.getColor(self.color, self,
                u'Choose line color', QColorDialog.ShowAlphaChannel)
        # Change the color for all shape lines:
        Shape.line_color = self.color
        self.canvas.repaint()

    def newLabel(self):
        self.canvas.deSelectShape()
        self.canvas.setEditing()

    def deleteSelectedShape(self):
        self.remLabel(self.canvas.deleteSelected())


class LabelDelegate(QItemDelegate):
    def __init__(self, parent=None):
        super(LabelDelegate, self).__init__(parent)
        self.validator = labelValidator()

    # FIXME: Validation and trimming are completely broken if the
    # user navigates away from the editor with something like TAB.
    def createEditor(self, parent, option, index):
        """Make sure the user cannot enter empty labels.
        Also remove trailing whitespace."""
        edit = super(LabelDelegate, self).createEditor(parent, option, index)
        if isinstance(edit, QLineEdit):
            edit.setValidator(self.validator)
            def strip():
                edit.setText(edit.text().trimmed())
            edit.editingFinished.connect(strip)
        return edit

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


def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except:
        return default

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

