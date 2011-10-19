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

from lib import struct, newAction, newIcon, addActions, fmtShortcut
from shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from canvas import Canvas
from zoomWidget import ZoomWidget
from labelDialog import LabelDialog
from simpleLabelDialog import SimpleLabelDialog
from colorDialog import ColorDialog
from labelFile import LabelFile, LabelFileError
from toolBar import ToolBar


__appname__ = 'labelme'

# FIXME
# - [medium] Set max zoom value to something big enough for FitWidth/Window
# - [medium] Disabling the save button prevents the user from saving to
#   alternate files. Either keep enabled, or add "Save As" button.

# TODO:
# - [high] Deselect shape when clicking and already selected(?)
# - [high] More sensible shortcuts (e.g. Ctrl+C to copy).
# - [high] Figure out WhatsThis for help.
# - [medium] Zoom should keep the image centered.
# - [high] Escape should cancel editing mode if no point in canvas.
# - [medium] Add undo button for vertex addition.
# - [medium,maybe] Support vertex moving.
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

        # Whether we need to save or not.
        self.dirty = False

        self._noSelectionSlot = False

        # Main widgets and related state.
        self.labelDialog = LabelDialog(parent=self)

        self.labelList = QListWidget()
        self.itemsToShapes = {}
        self.shapesToItems = {}

        self.labelList.itemActivated.connect(self.labelSelectionChanged)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        self.labelList.itemDoubleClicked.connect(self.editLabel)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)

        self.dock = QDockWidget(u'Polygon Labels', self)
        self.dock.setObjectName(u'Labels')
        self.dock.setWidget(self.labelList)

        self.zoomWidget = ZoomWidget()
        self.colorDialog = ColorDialog(parent=self)
        self.simpleLabelDialog = SimpleLabelDialog(parent=self)

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
                'Ctrl+Q', 'quit', u'Quit application')
        open = action('&Open', self.openFile,
                'Ctrl+O', 'open', u'Open image or label file')
        save = action('&Save', self.saveFile,
                'Ctrl+S', 'save', u'Save labels to file', enabled=False)
        close = action('&Close', self.closeFile,
                'Ctrl+K', 'close', u'Close current file')
        color1 = action('Polygon &Line Color', self.chooseColor1,
                'Ctrl+C', 'color', u'Choose polygon line color')
        color2 = action('Polygon &Fill Color', self.chooseColor2,
                'Ctrl+Shift+C', 'color', u'Choose polygon fill color')
        label = action('&New Polygon', self.newLabel,
                'Ctrl+N', 'new', u'Start a new polygon', enabled=False)
        copy = action('&Copy Polygon', self.copySelectedShape,
                'Ctrl+C', 'copy', u'Copy selected polygon', enabled=False)
        delete = action('&Delete Polygon', self.deleteSelectedShape,
                ['Ctrl+D', 'Delete'], 'delete', u'Delete', enabled=False)
        hide = action('&Hide Polygons', self.hideLabelsToggle,
                'Ctrl+H', 'hide', u'Hide all polygons',
                checkable=True)

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            u"Zoom in or out of the image. Also accessible with"\
             " %s and %s from the canvas." % (fmtShortcut("Ctrl+[-+]"),
                 fmtShortcut("Ctrl+Wheel")))
        self.zoomWidget.setEnabled(False)

        zoomIn = action('Zoom &In', partial(self.addZoom, 10),
                'Ctrl++', 'zoom-in', u'Increase zoom level', enabled=False)
        zoomOut = action('&Zoom Out', partial(self.addZoom, -10),
                'Ctrl+-', 'zoom-out', u'Decrease zoom level', enabled=False)
        zoomOrg = action('&Original size', partial(self.setZoom, 100),
                'Ctrl+=', 'zoom', u'Zoom to original size', enabled=False)
        fitWindow = action('&Fit Window', self.setFitWindow,
                'Ctrl+F', 'fit-window', u'Zoom follows window size',
                checkable=True, enabled=False)
        fitWidth = action('Fit &Width', self.setFitWidth,
                'Ctrl+W', 'fit-width', u'Zoom follows window width',
                checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoomActions = (self.zoomWidget, zoomIn, zoomOut, zoomOrg, fitWindow, fitWidth)
        self.zoomMode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action('&Edit Label', self.editLabel,
                'Ctrl+E', 'edit', u'Modify the label of the selected polygon',
                enabled=False)

        shapeLineColor = action('&Shape Line Color', self.chshapeLineColor,
                icon='color', tip=u'Change the line color for this specific shape',
                enabled=False)
        shapeFillColor = action('&Shape Fill Color', self.chshapeFillColor,
                icon='color', tip=u'Change the fill color for this specific shape',
                enabled=False)

        # Custom context menu for the canvas widget:
        addActions(self.canvas.menus[0], (label, edit, copy, delete))

        addActions(self.canvas.menus[0], (
            label, edit, copy, delete,
            shapeLineColor, shapeFillColor))
        addActions(self.canvas.menus[1], (
            action('&Copy here', self.copyShape),
            action('&Move here', self.moveShape)))

        labels = self.dock.toggleViewAction()
        labels.setText('Show/Hide Label Panel')
        labels.setShortcut('Ctrl+L')

        # Lavel list context menu.
        labelMenu = QMenu()
        addActions(labelMenu, (edit, delete))
        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(self.popLabelListMenu)
        # Add the action to the main window, so that its shortcut is global.
        self.addAction(edit)

        # Store actions for further handling.
        self.actions = struct(save=save, open=open, close=close,
                lineColor=color1, fillColor=color2,
                label=label, delete=delete, edit=edit, copy=copy,
                shapeLineColor=shapeLineColor, shapeFillColor=shapeFillColor,
                zoom=zoom, zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
                fitWindow=fitWindow, fitWidth=fitWidth,
                zoomActions=zoomActions,
                fileMenuActions=(open,save,close,quit))

        self.menus = struct(
                file=self.menu('&File'),
                edit=self.menu('&Polygons'),
                view=self.menu('&View'),
                labelList=labelMenu)
        addActions(self.menus.edit, (label, color1, color2))
        addActions(self.menus.view, (
            labels, None,
            zoomIn, zoomOut, zoomOrg, None,
            fitWindow, fitWidth))
        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        self.tools = self.toolbar('Tools')
        addActions(self.tools, (
            open, save, None,
            label, delete, hide, None,
            zoomIn, zoom, zoomOut, fitWindow, fitWidth))

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.filename = filename
        self.recentFiles = []
        self.maxRecent = 5
        self.lineColor = None
        self.fillColor = None
        self.zoom_level = 100
        self.fit_window = False

        # XXX: Could be completely declarative.
        # Restore application settings.
        types = {
            'filename': QString,
            'recentFiles': QStringList,
            'window/size': QSize,
            'window/position': QPoint,
            'window/geometry': QByteArray,
            # Docks and toolbars:
            'window/state': QByteArray,
        }
        self.settings = settings = Settings(types)
        self.recentFiles = list(settings['recentFiles'])
        size = settings.get('window/size', QSize(600, 500))
        position = settings.get('window/position', QPoint(0, 0))
        self.resize(size)
        self.move(position)
        # or simply:
        #self.restoreGeometry(settings['window/geometry']
        self.restoreState(settings['window/state'])
        self.lineColor = QColor(settings.get('line/color', Shape.line_color))
        self.fillColor = QColor(settings.get('fill/color', Shape.fill_color))
        Shape.line_color = self.lineColor
        Shape.fill_color = self.fillColor

        # Populate the File menu dynamically.
        self.updateFileMenu()
        # Since loading the file may take some time, make sure it runs in the background.
        self.queueEvent(partial(self.loadFile, self.filename))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        #self.firstStart = True
        #if self.firstStart:
        #    QWhatsThis.enterWhatsThisMode()

    ## Support Functions ##

    def setDirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.label.setEnabled(True)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        self.actions.close.setEnabled(value)

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.itemsToShapes.clear()
        self.shapesToItems.clear()
        self.labelList.clear()
        self.filename = None
        self.imageData = None
        self.labelFile = None
        self.canvas.resetState()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filename):
        if filename in self.recentFiles:
            self.recentFiles.remove(filename)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop()
        self.recentFiles.insert(0, filename)

    ## Callbacks ##

    def updateFileMenu(self):
        current = self.filename
        def exists(filename):
            return os.path.exists(unicode(filename))
        menu = self.menus.file
        menu.clear()
        files = [f for f in self.recentFiles if f != current and exists(f)]
        addActions(menu, self.actions.fileMenuActions)
        if files:
            menu.addSeparator()
            icon = newIcon('labels')
            for i, f in enumerate(files):
                action = QAction(
                    icon, '&%d %s' % (i+1, QFileInfo(f).fileName()), self)
                action.triggered.connect(partial(self.loadFile, f))
                menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def editLabel(self, item=None):
        item = item if item else self.currentItem()
        text = self.simpleLabelDialog.popUp(item.text())
        if text is not None:
            item.setText(text)
            self.setDirty()

    # React to canvas signals.
    def shapeSelectionChanged(self, selected=False):
        if self._noSelectionSlot:
            self._noSelectionSlot = False
        else:
            shape = self.canvas.selectedShape
            if shape:
                self.labelList.setItemSelected(self.shapesToItems[shape], True)
            else:
                self.labelList.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def addLabel(self, shape):
        item = QListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.itemsToShapes[item] = shape
        self.shapesToItems[shape] = item
        self.labelList.addItem(item)

    def remLabel(self, shape):
        item = self.shapesToItems.get(shape, None)
        self.labelList.takeItem(self.labelList.row(item))

    def loadLabels(self, shapes):
        s = []
        for label, points, line_color, fill_color in shapes:
            shape = Shape(label=label)
            for x, y in points:
                shape.addPoint(QPointF(x, y))
            s.append(shape)
            self.addLabel(shape)
            if line_color:
                shape.line_color = QColor(*line_color)
            if fill_color:
                shape.fill_color = QColor(*fill_color)
        self.canvas.loadShapes(s)

    def saveLabels(self, filename):
        lf = LabelFile()
        def format_shape(s):
            return dict(label=unicode(s.label),
                        line_color=s.line_color.getRgb()\
                                if s.line_color != self.lineColor else None,
                        fill_color=s.fill_color.getRgb()\
                                if s.fill_color != self.fillColor else None,
                        points=[(p.x(), p.y()) for p in s.points])

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        try:
            lf.save(filename, shapes, unicode(self.filename), self.imageData,
                self.lineColor.getRgb(), self.fillColor.getRgb())
            return True
        except LabelFileError, e:
            self.errorMessage(u'Error saving label data',
                    u'<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())
        #fix copy and delete
        self.shapeSelectionChanged(True)

    def labelSelectionChanged(self):
        item = self.currentItem()
        if item and not self.canvas.editing():
            self._noSelectionSlot = True
            self.canvas.selectShape(self.itemsToShapes[item])

    def labelItemChanged(self, item):
        shape = self.itemsToShapes[item]
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
        action = self.labelDialog.popUp(text='Enter name', position=position)
        if action == self.labelDialog.OK:
            self.addLabel(self.canvas.setLastLabel(self.labelDialog.text()))
            self.actions.label.setEnabled(True)
            self.setDirty()
        elif action == self.labelDialog.UNDO:
            self.canvas.undoLastLine()
        elif action == self.labelDialog.DELETE:
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
        #self.canvas.hideBackroundShapes(value)
        for item, shape in self.itemsToShapes.iteritems():
            item.setCheckState(Qt.Unchecked if value else Qt.Checked)

    def loadFile(self, filename=None):
        """Load the specified file, or the last opened file if None."""
        self.resetState()
        self.canvas.setEnabled(False)
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
                self.lineColor = QColor(*self.labelFile.lineColor)
                self.fillColor = QColor(*self.labelFile.fillColor)
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
            self.canvas.loadPixmap(QPixmap.fromImage(image))
            if self.labelFile:
                self.loadLabels(self.labelFile.shapes)
            self.setClean()
            self.canvas.setEnabled(True)
            self.adjustScale()
            self.paintCanvas()
            self.addRecentFile(self.filename)
            self.toggleActions(True)
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
        self.canvas.update()

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
        s['line/color'] = self.lineColor
        s['fill/color'] = self.fillColor
        s['recentFiles'] = self.recentFiles
        # ask the use for where to save the labels
        #s['window/geometry'] = self.saveGeometry()

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
        assert self.itemsToShapes, "cannot save empty labels"
        formats = ['*%s' % LabelFile.suffix]
        filename = unicode(QFileDialog.getSaveFileName(self,
            '%s - Choose File', self.currentPath(),
            'Label files (%s)' % ''.join(formats)))
        if filename:
            if self.saveLabels(filename):
                self.addRecentFile(filename)
                self.setClean()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)

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

    def chooseColor1(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                default=DEFAULT_LINE_COLOR)
        if color:
            self.lineColor = color
            # Change the color for all shape lines:
            Shape.line_color = self.lineColor
            self.canvas.update()
            self.setDirty()

    def chooseColor2(self):
       color = self.colorDialog.getColor(self.fillColor, u'Choose fill color',
                default=DEFAULT_FILL_COLOR)
       if color:
            self.fillColor = color
            Shape.fill_color = self.fillColor
            self.canvas.update()
            self.setDirty()

    def newLabel(self):
        self.canvas.deSelectShape()
        self.canvas.setEditing()
        self.actions.label.setEnabled(False)

    def deleteSelectedShape(self):
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'You are about to permanently delete this polygon, proceed anyway?'
        if yes == QMessageBox.warning(self, u'Attention', msg, yes|no):
            self.remLabel(self.canvas.deleteSelected())
            self.setDirty()

    def chshapeLineColor(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selectedShape.line_color = color
            self.canvas.update()
            self.setDirty()

    def chshapeFillColor(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selectedShape.fill_color = color
            self.canvas.update()
            self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.addLabel(self.canvas.selectedShape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()


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

