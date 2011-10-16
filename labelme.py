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

from lib import struct, newAction, addActions, labelValidator
from shape import Shape
from canvas import Canvas
from zoomWidget import ZoomWidget
from labelDialog import LabelDialog
from labelFile import LabelFile, LabelFileError
from toolBar import ToolBar


__appname__ = 'labelme'

# FIXME
# - [medium] Set max zoom value to something big enough for FitWidth/Window
# - [medium] Disabling the save button prevents the user from saving to
#   alternate files. Either keep enabled, or add "Save As" button.
# - [low] Label validation/postprocessing breaks with TAB.

# TODO:
# - [high] Only fill shapes on mouse-over.
# - [medium] Highlight label list on shape selection and vice-verca.
# - [medium] Add undo button for vertex addition.
# - [medium,maybe] Support vertex moving.
# - [low,easy] Add button to Hide/Show all labels.
# - [low,maybe] Open images with drag & drop.
# - [low,maybe] Preview images on file dialogs.
# - [low,maybe] Sortable label list.
# - [extra] Add beginner/advanced mode, where different settings are set for
#   the application, e.g. closable labels, different toolbuttons etc.
# - Zoom is too "steppy".


### Utility functions and classes.

class WindowMixin(object):
    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        #toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = range(3)

    def __init__(self, filename=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        # Not sure this does anything really.
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        # Whether we need to save or not.
        self.dirty = False

        # Main widgets.
        self.label = LabelDialog(parent=self)
        self.labels = {}
        self.items = {}
        self.highlighted = None
        self.labelList = QListWidget()
        self.dock = QDockWidget(u'Labels', self)
        self.dock.setObjectName(u'Labels')
        self.dock.setWidget(self.labelList)
        self.zoomWidget = ZoomWidget()

        self.labelList.setItemDelegate(LabelDelegate())
        self.labelList.itemActivated.connect(self.highlightLabel)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)

        self.canvas = Canvas()
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
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)

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
                'Ctrl+N', 'new', u'Add new label', enabled=False)
        copy = action('&Copy', self.copySelectedShape,
                'Ctrl+C', 'copy', u'Copy', enabled=False)
        delete = action('&Delete', self.deleteSelectedShape,
                ['Ctrl+D', 'Delete'], 'delete', u'Delete', enabled=False)
        hide = action('&Hide labels', self.hideLabelsToggle,
                'Ctrl+H', 'hide', u'Hide background labels when drawing',
                checkable=True)

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        zoomIn = action('Zoom &In', partial(self.addZoom, 10),
                'Ctrl++', 'zoom-in', u'Increase zoom level')
        zoomOut = action('&Zoom Out', partial(self.addZoom, -10),
                'Ctrl+-', 'zoom-out', u'Decrease zoom level')
        zoomOrg = action('&Original size', partial(self.setZoom, 100),
                'Ctrl+=', 'zoom', u'Zoom to original size')
        fitWindow = action('&Fit Window', self.setFitWindow,
                'Ctrl+F', 'fit-window', u'Zoom follows window size',
                checkable=True)
        fitWidth = action('Fit &Width', self.setFitWidth,
                'Ctrl+W', 'fit-width', u'Zoom follows window width',
                checkable=True)
        self.zoomMode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
        }

        # Custom context menu for the canvas widget:
        addActions(self.canvas.menus[0], (label, copy, delete))
        addActions(self.canvas.menus[1], (
            action('&Copy here', self.copyShape),
            action('&Move here', self.moveShape)))

        labels = self.dock.toggleViewAction()
        labels.setShortcut('Ctrl+L')

        # Store actions for further handling.
        self.actions = struct(save=save, open=open, color=color,
                label=label, delete=delete, zoom=zoom, copy=copy,
                zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
                fitWindow=fitWindow, fitWidth=fitWidth)
        save.setEnabled(False)

        self.menus = struct(
                file=self.menu('&File'),
                edit=self.menu('&Image'),
                view=self.menu('&View'))
        addActions(self.menus.file, (open, save, quit))
        addActions(self.menus.edit, (label, color, fitWindow, fitWidth))
        addActions(self.menus.view, (
            labels, None,
            zoomIn, zoomOut, zoomOrg, None,
            fitWindow, fitWidth))

        self.tools = self.toolbar('Tools')
        addActions(self.tools, (
            open, save, None,
            label, delete, color, hide, None,
            zoomIn, zoom, zoomOut, fitWindow, fitWidth, None,
            quit))

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.filename = filename
        self.recent_files = []
        self.color = None
        self.zoom_level = 100
        self.fit_window = False

        # XXX: Could be completely declarative.
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
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

    ## Support Functions ##

    def setDirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.label.setEnabled(True)

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    ## Callbacks ##

    # React to canvas signals.
    def shapeSelectionChanged(self, selected=False):
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)

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
        try:
            lf.save(filename, shapes, unicode(self.filename), self.imageData)
            return True
        except LabelFileError, e:
            self.errorMessage(u'Error saving label data',
                    u'<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())
        #fix copy and delete
        self.shapeSelectionChanged(True)

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
            shape.label = unicode(item.text())
            self.setDirty()
        else: # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    ## Callback functions:
    def newShape(self, position):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        action = self.label.popUp(position)
        if action == self.label.OK:
            self.addLabel(self.canvas.setLastLabel(self.label.text()))
            self.setDirty()
            # Enable appropriate actions.
            self.actions.label.setEnabled(True)
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

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)

    def addZoom(self, increment=10):
        self.setZoom(self.zoomWidget.value() + increment)

    def zoomRequest(self, delta):
        units = delta / (8 * 15)
        scale = 10
        self.addZoom(scale * units)

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def hideLabelsToggle(self, value):
        self.canvas.hideBackroundShapes(value)

    def loadFile(self, filename=None):
        """Load the specified file, or the last opened file if None."""
        if filename is None:
            filename = self.settings['filename']
        filename = unicode(filename)
        if QFile.exists(filename):
            if LabelFile.isLabelFile(filename):
                try:
                    self.labelFile = LabelFile(filename)
                except LabelFileError, e:
                    self.errorMessage(u'Error opening file',
                            (u"<p><b>%s</b></p>"
                             u"<p>Make sure <i>%s</i> is a valid label file.")\
                            % (e, filename))
                    self.status("Error reading %s" % filename)
                    return False
                self.imageData = self.labelFile.imageData
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.imageData = read(filename, None)
                self.labelFile = None
            image = QImage.fromData(self.imageData)
            if image.isNull():
                self.errorMessage(u'Error opening file',
                        u"<p>Make sure <i>%s</i> is a valid image file." % filename)
                self.status("Error reading %s" % filename)
                return False
            self.status("Loaded %s" % os.path.basename(unicode(filename)))
            self.image = image
            self.filename = filename
            self.labels = {}
            self.labelList.clear()
            self.canvas.loadPixmap(QPixmap.fromImage(image))
            if self.labelFile:
                self.loadLabels(self.labelFile.shapes)
            self.setClean()
            return True
        return False

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull()\
           and self.zoomMode != self.MANUAL_ZOOM:
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.repaint()

    def adjustScale(self):
        self.zoomWidget.setValue(int(100 * self.scalers[self.zoomMode]()))

    def scaleFitWindow(self):
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

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
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

    ## User Dialogs ##

    def openFile(self, _value=False):
        if not self.mayContinue():
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

    def saveFile(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        assert self.labels, "cannot save empty labels"
        formats = ['*%s' % LabelFile.suffix]
        filename = unicode(QFileDialog.getSaveFileName(self,
            '%s - Choose File', self.currentPath(),
            'Label files (%s)' % ''.join(formats)))
        if filename:
            if self.saveLabels(filename):
                self.setClean()

    # Message Dialogs. #
    def mayContinue(self):
        return not (self.dirty and not self.discardChangesDialog())

    def discardChangesDialog(self):
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'You have unsaved changes, proceed anyway?'
        return yes == QMessageBox.warning(self, u'Attention', msg, yes|no)

    def errorMessage(self, title, message):
        return QMessageBox.critical(self, title,
                '<p><b>%s</b></p>%s' % (title, message))

    def currentPath(self):
        return os.path.dirname(unicode(self.filename)) if self.filename else '.'

    def chooseColor(self):
        self.color = QColorDialog.getColor(self.color, self,
                u'Choose line color', QColorDialog.ShowAlphaChannel)
        # Change the color for all shape lines:
        Shape.line_color = self.color
        self.canvas.repaint()

    def newLabel(self):
        self.canvas.deSelectShape()
        self.canvas.setEditing()
        self.actions.label.setEnabled(False)

    def deleteSelectedShape(self):
        self.remLabel(self.canvas.deleteSelected())
        self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.addLabel(self.canvas.selectedShape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()


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


def main(argv):
    """Standard boilerplate Qt application code."""
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    win = MainWindow(argv[1] if len(argv) == 2 else None)
    win.show()
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main(sys.argv))

