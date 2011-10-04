
from math import sqrt

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from shape import Shape

class Canvas(QLabel):
    done = pyqtSignal()
    epsilon = 7.0 # TODO: Tune value

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        self.shapes = []
        self.current = None
        self.line = Shape(line_color=QColor(0, 0, 255))

    def mousePressEvent(self, ev):
        if ev.button() == 1:
            if self.current:
                self.current.vertices.append(ev.pos())
                if self.isClosed():
                    self.finalise()
                self.repaint()
            else:
                self.current = Shape()
                self.current.vertices.append(ev.pos())
                self.setMouseTracking(True)

    def mouseDoubleClickEvent(self, ev):
        if self.current:
            self.current.vertices.append(self.current[0])
            self.finalise()

    def finalise(self):
        assert self.current
        self.current.fill = True
        self.shapes.append(self.current)
        self.current = None
        # TODO: Mouse tracking is still useful for selecting shapes!
        self.setMouseTracking(False)
        self.repaint()
        self.done.emit()

    def isClosed(self):
        assert self.current
        return len(self.current) > 1\
           and self.closeEnough()
        return len(self.points) > 1 and self.closeEnough(self.points[0], self.points[-1])

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        if self.current:
            self.line.vertices = (self.current[-1], ev.pos())
            self.repaint()

    def closeEnough(self):
        assert self.current
        def distance(p):
            return sqrt(p.x() * p.x() + p.y() * p.y())
        p1, p2 = self.current.vertices[0], self.current.vertices[-1]
        d = distance(p1 - p2)
        m = (p1-p2).manhattanLength()
        print "d %.2f, m %d, %.2f" % (d, m, d - m)
        return distance(p1 - p2) < self.epsilon

    def paintEvent(self, event):
        super(Canvas, self).paintEvent(event)
        qp = QPainter()
        qp.begin(self)
        for shape in self.shapes:
            shape.paint(qp)
        if self.current:
            self.current.paint(qp)
            self.line.paint(qp)
        qp.end()

