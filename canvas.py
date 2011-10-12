
from math import sqrt

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from shape import Shape

class Canvas(QWidget):
    zoomRequest = pyqtSignal(int)
    scrollRequest = pyqtSignal(int, int)
    newShape = pyqtSignal(QPoint)

    SELECT, EDIT = range(2)

    epsilon = 9.0 # TODO: Tune value

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
        self.prevPoint=QPoint()
        self.scale = 1.0
        self.pixmap = None
        # Set widget options.
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)

    def editing(self):
        return self.mode == self.EDIT

    def setEditing(self, value=True):
        self.mode = self.EDIT if value else self.SELECT

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        if ev.button() == Qt.RightButton:
            if self.selectedShapeCopy:
                if self.prevPoint:
                    point=QPoint(self.prevPoint)
                    dx= ev.x()-point.x()
                    dy=ev.y()-point.y()
                    self.selectedShapeCopy.moveBy(dx,dy)
                    self.repaint()
                self.prevPoint=ev.pos()
            elif self.selectedShape:
                newShape=Shape()
                for point in self.selectedShape.points:
                    newShape.addPoint(point)
                self.selectedShapeCopy=newShape
                self.repaint()
            return

        # Polygon drawing.
        if self.current and self.editing():
            pos = self.transformPos(ev.posF())
            color = self.lineColor
            if self.outOfPixmap(pos):
                # Don't allow the user to draw outside the pixmap.
                # Project the point to the pixmap's edges.
                pos = self.intersectionPoint(pos)
            elif len(self.current) > 1 and self.closeEnough(pos, self.current[0]):
                # Attract line to starting point and colorise to alert the user:
                # TODO: I would also like to highlight the pixel somehow.
                pos = self.current[0]
                color = self.current.line_color
            self.line[1] = pos
            self.line.line_color = color
            self.repaint()
            return

        if self.selectedShape:
            if self.prevPoint:
                    point=QPoint(self.prevPoint)
                   # print point.x()
                    dx= ev.x()-point.x()
                    dy=ev.y()-point.y()
                    self.selectedShape.moveBy(dx,dy)
                    self.repaint()
            self.prevPoint=ev.pos()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            if self.editing():
                if self.current:
                    self.current.addPoint(self.line[1])
                    self.line[0] = self.current[-1]
                    if self.current.isClosed():
                        self.finalise(ev)
                else:
                    pos = self.transformPos(ev.posF())
                    if self.outOfPixmap(pos):
                        return
                    self.current = Shape()
                    self.line.points = [pos, pos]
                    self.current.addPoint(pos)
            else:
                self.selectShape(ev.pos())
                self.prevPoint=ev.pos()
            self.repaint()

    def mouseDoubleClickEvent(self, ev):
        if self.current and self.editing():
            # Add first point in the list so that it is consistent
            # with shapes created the normal way.
            self.current.addPoint(self.current[0])
            self.finalise(ev)

    def selectShape(self, point):
        """Select the first shape created which contains this point."""
        self.deSelectShape()
        for shape in self.shapes:
            if shape.containsPoint(point):
                shape.selected = True
                self.selectedShape = shape
                return self.repaint()

    def deSelectShape(self):
        if self.selectedShape:
            self.selectedShape.selected = False
            self.repaint()

    def deleteSelected(self):
        if self.selectedShape:
             self.shapes.remove(self.selectedShape)
             self.selectedShape=None
             #print self.selectedShape()
             self.repaint()

    def paintEvent(self, event):
        if not self.pixmap:
            return super(Canvas, self).paintEvent(event)

        p = QPainter()
        p.begin(self)
        p.setRenderHint(QPainter.Antialiasing)

        p.scale(self.scale, self.scale)
        p.translate(self.offsetToCenter())

        p.drawPixmap(0, 0, self.pixmap)
        Shape.scale = self.scale
        for shape in self.shapes:
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
        self.current.fill = True
        self.shapes.append(self.current)
        self.current = None
        self.setEditing(False)
        self.repaint()
        self.newShape.emit(self.mapToGlobal(ev.pos()))

    def closeEnough(self, p1, p2):
        #d = distance(p1 - p2)
        #m = (p1-p2).manhattanLength()
        #print "d %.2f, m %d, %.2f" % (d, m, d - m)
        return distance(p1 - p2) < self.epsilon

    def intersectionPoint(self, mousePos):
        # Cycle through each image edge in clockwise fashion,
        # and find the one intersecting the current line segment.
        # http://paulbourke.net/geometry/lineline2d/
        size = self.pixmap.size()
        points = [(0,0),
                  (size.width(), 0),
                  (size.width(), size.height()),
                  (0, size.height())]
        x1, y1 = self.current[-1].x(), self.current[-1].y()
        x2, y2 = mousePos.x(), mousePos.y()
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

    def undoLastLine(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.fill = False
        pos = self.current.popPoint()
        self.line.points = [self.current[-1], pos]
        self.setEditing()

    def deleteLastShape(self):
        assert self.shapes
        self.shapes.pop()


def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())

