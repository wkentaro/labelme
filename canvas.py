
from math import sqrt

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from shape import Shape

# TODO:
# - [maybe] Add 2 painters, one for the pixmap one for the shape,
#   since performance on big images is a problem...
# - [maybe] Highlight source vertex when "attracting" line.
# - [maybe] Find optimal epsilon value.

CURSOR_DEFAULT = Qt.ArrowCursor
CURSOR_DRAW    = Qt.CrossCursor
CURSOR_MOVE    = Qt.ClosedHandCursor
CURSOR_GRAB    = Qt.OpenHandCursor

class Canvas(QWidget):
    zoomRequest = pyqtSignal(int)
    scrollRequest = pyqtSignal(int, int)
    newShape = pyqtSignal(QPoint)
    selectionChanged = pyqtSignal(bool)
    shapeMoved = pyqtSignal()

    SELECT, EDIT = range(2)

    epsilon = 9.0

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        # Initialise local state.
        self.mode = self.SELECT
        self.shapes = []
        self.current = None
        self.selectedShape=None # save the selected shape here
        self.selectedShapeCopy=None
        self.lineColor = QColor(0, 0, 255)
        self.line = Shape(line_color=self.lineColor)
        self.mouseButtonIsPressed=False #when it is true and shape is selected , move the shape with the mouse move event
        self.prevPoint = QPointF()
        self.offsets = QPointF(), QPointF()
        self.scale = 1.0
        self.pixmap = QPixmap()
        self.visible = {}
        self._hideBackround = False
        self.hideBackround = False
        self.highlightedShape = None
        # Menus:
        self.menus = (QMenu(), QMenu())
        # Set widget options.
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)

    def isVisible(self, shape):
        return self.visible.get(shape, True)

    def editing(self):
        return self.mode == self.EDIT

    def setEditing(self, value=True):
        self.mode = self.EDIT if value else self.SELECT

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        pos = self.transformPos(ev.posF())

        self.restoreCursor()

        # Polygon copy moving.
        if Qt.RightButton & ev.buttons():
            if self.selectedShapeCopy and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShape(self.selectedShapeCopy, pos)
                self.repaint()
            elif self.selectedShape:
                self.selectedShapeCopy = self.selectedShape.copy()
                self.selectedShapeCopy.line_color = QColor(255, 0, 0, 64)
                self.selectedShapeCopy.fill_color = QColor(0, 255, 0, 64)
                self.repaint()
            return

        # Polygon drawing.
        if self.editing():
            self.overrideCursor(CURSOR_DRAW)

        if self.current and self.editing():
            color = self.lineColor
            if self.outOfPixmap(pos):
                # Don't allow the user to draw outside the pixmap.
                # Project the point to the pixmap's edges.
                pos = self.intersectionPoint(self.current[-1], pos)
            elif len(self.current) > 1 and self.closeEnough(pos, self.current[0]):
                # Attract line to starting point and colorise to alert the user:
                pos = self.current[0]
                color = self.current.line_color
            self.line[1] = pos
            self.line.line_color = color
            self.repaint()
            return

        # Polygon moving.
        if Qt.LeftButton & ev.buttons() and self.selectedShape and self.prevPoint:
            self.overrideCursor(CURSOR_MOVE)
            self.boundedMoveShape(self.selectedShape, pos)
            self.shapeMoved.emit()
            self.repaint()
            return

        # Just hovering over the canvas:
        # Update tooltip value and fill topmost shape.
        self.setToolTip("Image")
        previous = self.highlightedShape
        for shape in reversed(self.shapes):
            if shape.containsPoint(pos) and self.isVisible(shape):
                self.setToolTip("Object '%s'" % shape.label)
                self.highlightedShape = shape
                self.overrideCursor(CURSOR_GRAB)
                break
        else:
            self.highlightedShape = None
        if previous != self.highlightedShape:
            # Try to minimise repaints.
            self.repaint()

    def mousePressEvent(self, ev):
        pos = self.transformPos(ev.posF())
        if ev.button() == Qt.LeftButton:
            if self.editing():
                if self.current:
                    self.current.addPoint(self.line[1])
                    self.line[0] = self.current[-1]
                    if self.current.isClosed():
                        self.finalise(ev)
                elif not self.outOfPixmap(pos):
                    self.current = Shape()
                    self.current.addPoint(pos)
                    self.line.points = [pos, pos]
                    self.setHiding()
                    self.repaint()
            else:
                self.selectShape(pos)
                self.prevPoint = pos
                self.repaint()
        elif ev.button() == Qt.RightButton and not self.editing():
            self.selectShape(pos)
            self.prevPoint = pos
            self.repaint()

    def mouseReleaseEvent(self, ev):
        pos = self.transformPos(ev.posF())
        if ev.button() == Qt.RightButton:
            menu = self.menus[bool(self.selectedShapeCopy)]
            self.restoreCursor()
            if not menu.exec_(self.mapToGlobal(ev.pos()))\
               and self.selectedShapeCopy:
                # Cancel the move by deleting the shadow copy.
                self.selectedShapeCopy = None
                self.repaint()
        elif ev.button() == Qt.LeftButton and self.selectedShape:
            self.overrideCursor(CURSOR_GRAB)

    def endMove(self, copy=False):
        assert self.selectedShape and self.selectedShapeCopy
        shape = self.selectedShapeCopy
        del shape.fill_color
        del shape.line_color
        if copy:
            self.shapes.append(shape)
            self.selectedShape.selected = False
            self.selectedShape = shape
            self.repaint()
        else:
            shape.label = self.selectedShape.label
            self.deleteSelected()
            self.shapes.append(shape)
        self.selectedShapeCopy = None

    def hideBackroundShapes(self, value):
        self.hideBackround = value
        if self.selectedShape:
            # Only hide other shapes if there is a current selection.
            # Otherwise the user will not be able to select a shape.
            self.setHiding(True)
            self.repaint()

    def setHiding(self, enable=True):
        self._hideBackround = self.hideBackround if enable else False

    def mouseDoubleClickEvent(self, ev):
        if self.current and self.editing():
            # Shapes need to have at least 3 vertices.
            if len(self.current) < 4:
                return
            # Replace the last point with the starting point.
            # We have to do this because the mousePressEvent handler
            # adds that point before this handler is called!
            self.current[-1] = self.current[0]
            self.finalise(ev)

    def selectShape(self, point):
        """Select the first shape created which contains this point."""
        self.deSelectShape()
        for shape in reversed(self.shapes):
            if self.isVisible(shape) and shape.containsPoint(point):
                shape.selected = True
                self.selectedShape = shape
                self.calculateOffsets(shape, point)
                self.setHiding()
                self.selectionChanged.emit(True)
                return

    def calculateOffsets(self, shape, point):
        rect = shape.boundingRect()
        x1 = rect.x() - point.x()
        y1 = rect.y() - point.y()
        x2 = (rect.x() + rect.width()) - point.x()
        y2 = (rect.y() + rect.height()) - point.y()
        self.offsets = QPointF(x1, y1), QPointF(x2, y2)

    def boundedMoveShape(self, shape, pos):
        if self.outOfPixmap(pos):
            return # No need to move
        o1 = pos + self.offsets[0]
        if self.outOfPixmap(o1):
            pos -= QPointF(min(0, o1.x()), min(0, o1.y()))
        o2 = pos + self.offsets[1]
        if self.outOfPixmap(o2):
            pos += QPointF(min(0, self.pixmap.width() - o2.x()),
                           min(0, self.pixmap.height()- o2.y()))
        # The next line tracks the new position of the cursor
        # relative to the shape, but also results in making it
        # a bit "shaky" when nearing the border and allows it to
        # go outside of the shape's area for some reason. XXX
        #self.calculateOffsets(self.selectedShape, pos)
        shape.moveBy(pos - self.prevPoint)
        self.prevPoint = pos

    def deSelectShape(self):
        if self.selectedShape:
            self.selectedShape.selected = False
            self.selectedShape = None
            self.setHiding(False)
            self.repaint()
            self.selectionChanged.emit(False)

    def deleteSelected(self):
        if self.selectedShape:
            shape = self.selectedShape
            self.shapes.remove(self.selectedShape)
            self.selectedShape = None
            self.repaint()
            return shape

    def copySelectedShape(self):
        if self.selectedShape:
            shape = self.selectedShape.copy()
            self.shapes.append(shape)
            self.selectedShape = shape
            self.deSelectShape()
            self.repaint()
            return shape

    def paintEvent(self, event):
        if not self.pixmap:
            return super(Canvas, self).paintEvent(event)

        p = QPainter()
        p.begin(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        p.scale(self.scale, self.scale)
        p.translate(self.offsetToCenter())

        p.drawPixmap(0, 0, self.pixmap)
        Shape.scale = self.scale
        for shape in self.shapes:
            if (shape.selected or not self._hideBackround) and self.isVisible(shape):
                shape.fill = shape.selected or self.highlightedShape == shape
                shape.paint(p)
        if self.current:
            self.current.paint(p)
            self.line.paint(p)
        if self.selectedShapeCopy:
            self.selectedShapeCopy.paint(p)

        p.end()

    def transformPos(self, point):
        """Convert from widget-logical coordinates to painter-logical coordinates."""
        return point / self.scale - self.offsetToCenter()

    def offsetToCenter(self):
        s = self.scale
        area = super(Canvas, self).size()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        aw, ah = area.width(), area.height()
        x = (aw-w)/(2*s) if aw > w else 0
        y = (ah-h)/(2*s) if ah > h else 0
        return QPointF(x, y)

    def outOfPixmap(self, p):
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w and 0 <= p.y() <= h)

    def finalise(self, ev):
        assert self.current
        self.shapes.append(self.current)
        self.current = None
        self.setEditing(False)
        self.setHiding(False)
        self.repaint()
        self.newShape.emit(self.mapToGlobal(ev.pos()))

    def closeEnough(self, p1, p2):
        #d = distance(p1 - p2)
        #m = (p1-p2).manhattanLength()
        #print "d %.2f, m %d, %.2f" % (d, m, d - m)
        return distance(p1 - p2) < self.epsilon

    def intersectionPoint(self, p1, p2):
        # Cycle through each image edge in clockwise fashion,
        # and find the one intersecting the current line segment.
        # http://paulbourke.net/geometry/lineline2d/
        size = self.pixmap.size()
        points = [(0,0),
                  (size.width(), 0),
                  (size.width(), size.height()),
                  (0, size.height())]
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        d, i, (x, y) = min(self.intersectingEdges((x1, y1), (x2, y2), points))
        x3, y3 = points[i]
        x4, y4 = points[(i+1)%4]
        if (x, y) == (x1, y1):
            # Handle cases where previous point is on one of the edges.
            if x3 == x4:
                return QPointF(x3, min(max(0, y2), max(y3, y4)))
            else: # y3 == y4
                return QPointF(min(max(0, x2), max(x3, x4)), y3)
        return QPointF(x, y)

    def intersectingEdges(self, (x1, y1), (x2, y2), points):
        """For each edge formed by `points', yield the intersection
        with the line segment `(x1,y1) - (x2,y2)`, if it exists.
        Also return the distance of `(x2,y2)' to the middle of the
        edge along with its index, so that the one closest can be chosen."""
        for i in xrange(4):
            x3, y3 = points[i]
            x4, y4 = points[(i+1) % 4]
            denom = (y4-y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
            nua = (x4-x3) * (y1-y3) - (y4-y3) * (x1-x3)
            nub = (x2-x1) * (y1-y3) - (y2-y1) * (x1-x3)
            if denom == 0:
                # This covers two cases:
                #   nua == nub == 0: Coincident
                #   otherwise: Parallel
                continue
            ua, ub = nua / denom, nub / denom
            if 0 <= ua <= 1 and 0 <= ub <= 1:
                x = x1 + ua * (x2 - x1)
                y = y1 + ua * (y2 - y1)
                m = QPointF((x3 + x4)/2, (y3 + y4)/2)
                d = distance(m - QPointF(x2, y2))
                yield d, i, (x, y)

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        if self.pixmap:
            return self.scale * self.pixmap.size()
        return super(Canvas, self).minimumSizeHint()

    def wheelEvent(self, ev):
        if ev.orientation() == Qt.Vertical:
            mods = ev.modifiers()
            if Qt.ControlModifier == int(mods):
                self.zoomRequest.emit(ev.delta())
            else:
                self.scrollRequest.emit(ev.delta(),
                        Qt.Horizontal if (Qt.ShiftModifier == int(mods))\
                                      else Qt.Vertical)
        else:
            self.scrollRequest.emit(ev.delta(), Qt.Horizontal)
        ev.accept()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape and self.current:
            self.current = None
            self.repaint()

    def setLastLabel(self, text):
        assert text
        print "shape <- '%s'" % text
        self.shapes[-1].label = text
        return self.shapes[-1]

    def undoLastLine(self):
        assert self.shapes
        self.current = self.shapes.pop()
        pos = self.current.popPoint()
        self.line.points = [self.current[-1], pos]
        self.setEditing()

    def deleteLastShape(self):
        assert self.shapes
        self.shapes.pop()

    def loadPixmap(self, pixmap):
        self.pixmap = pixmap
        self.shapes = []
        self.repaint()

    def loadShapes(self, shapes):
        self.shapes = list(shapes)
        self.current = None
        self.repaint()

    def copySelectedShape(self):
        if self.selectedShape:
            newShape=self.selectedShape.copy()
            self.shapes.append(newShape)
            self.deSelectShape()
            self.shapes[-1].selected=True
            self.selectedShape=self.shapes[-1]
            self.repaint()
            return self.selectedShape

    def setShapeVisible(self, shape, value):
        self.visible[shape] = value
        self.repaint()

    def overrideCursor(self, cursor):
        QApplication.setOverrideCursor(cursor)

    def restoreCursor(self):
        QApplication.restoreOverrideCursor()


def pp(p):
    return '%.2f, %.2f' % (p.x(), p.y())

def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())

