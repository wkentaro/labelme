
from math import sqrt

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from shape import Shape

class Canvas(QWidget):
    zoomRequest = pyqtSignal(int)
    scrollRequest = pyqtSignal(int, int)

    epsilon = 9.0 # TODO: Tune value

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        self.startLabeling=False # has to click new label buttoon to starting drawing new polygons
        self.shapes = []
        self.current = None
        self.selectedShape=None # save the selected shape here
        self.selectedShapeCopy=None
        self.line_color = QColor(0, 0, 255)
        self.line = Shape(line_color=self.line_color)
        self.mouseButtonIsPressed=False #when it is true and shape is selected , move the shape with the mouse move event
        self.prevPoint=QPoint()
        
        self.scale = 1.0
        self.pixmap = None

        self.setFocusPolicy(Qt.WheelFocus)

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""

        if (ev.buttons() & 2):  # wont work , as ev.buttons doesn't work well , or I haven't known how to use it :) to use right click
            print ev.button()
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

        if self.current and self.startLabeling: 
            pos = self.transformPos(ev.posF())
            # Don't allow the user to draw outside of the pixmap area.
            # FIXME: Project point to pixmap's edge when getting out too fast
            if self.outOfPixmap(pos):
                return ev.ignore()
            if len(self.current) > 1 and self.closeEnough(pos, self.current[0]):
                # Attract line to starting point and colorise to alert the user:
                self.line[1] = self.current[0]
                self.line.line_color = self.current.line_color
            else:
                self.line[1] = pos
                self.line.line_color = self.line_color
            return self.repaint()
            
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
        if ev.button() == 1:
            if self.startLabeling:
                if self.current:
                    self.current.addPoint(self.line[1])
                    self.line[0] = self.current[-1]
                    if self.current.isClosed():
                        self.finalise()
                    self.repaint()
                else:
                    pos = self.transformPos(ev.posF())
                    self.current = Shape()
                    self.line.points = [pos, pos]
                    self.current.addPoint(pos)
                    self.setMouseTracking(True)
            else: # not in adding new label mode
                self.selectShape(ev.pos())
                self.prevPoint=ev.pos()
       
                

    def mouseDoubleClickEvent(self, ev):
        if self.current and self.startLabeling:
            # Add first point in the list so that it is consistent
            # with shapes created the normal way.
            self.current.addPoint(self.current[0])
            self.finalise()

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


    def finalise(self):
        assert self.current
        self.current.fill = True
        self.shapes.append(self.current)
        self.current = None
        self.startLabeling = False
        # TODO: Mouse tracking is still useful for selecting shapes!
        self.setMouseTracking(False)
        self.repaint()

    def closeEnough(self, p1, p2):
        #d = distance(p1 - p2)
        #m = (p1-p2).manhattanLength()
        #print "d %.2f, m %d, %.2f" % (d, m, d - m)
        return distance(p1 - p2) < self.epsilon


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
            self.setMouseTracking(False)
            self.repaint()


def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())

