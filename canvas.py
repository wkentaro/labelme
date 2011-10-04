
from math import sqrt

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from shape import Shape

class Canvas(QLabel):
    epsilon = 9.0 # TODO: Tune value

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        self.shapes = []
        self.current = None
        self.line_color = QColor(0, 0, 255)
        self.line = Shape(line_color=self.line_color)

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        if self.current:
            if len(self.current) > 1 and self.closeEnough(ev.pos(), self.current[0]):
                self.line[1] = self.current[0]
                self.line.line_color = self.current.line_color
            else:
                self.line[1] = ev.pos()
                self.line.line_color = self.line_color
            self.repaint()

    def mousePressEvent(self, ev):
        if ev.button() == 1:
            if self.current:
                self.current.addPoint(self.line[1])
                self.line[0] = self.current[-1]
                if self.current.isClosed():
                    self.finalise()
                self.repaint()
            else:
                self.current = Shape()
                self.line.points = [ev.pos(), ev.pos()]
                self.current.addPoint(ev.pos())
                self.setMouseTracking(True)

    def mouseDoubleClickEvent(self, ev):
        if self.current:
            #self.current.addPoint(self.current[0]) , you don't need this code ,point0 is already there (duplicate the same point)
            self.finalise()

    def paintEvent(self, event):
        super(Canvas, self).paintEvent(event)
        qp = QPainter()
        qp.begin(self)
        qp.setRenderHint(QPainter.Antialiasing)
        for shape in self.shapes:
            shape.paint(qp)
        if self.current:
            self.current.paint(qp)
            self.line.paint(qp)
        qp.end()


    def finalise(self):
        assert self.current
        self.current.fill = True
        self.shapes.append(self.current)
        self.current = None
        # TODO: Mouse tracking is still useful for selecting shapes!
        self.setMouseTracking(False)
        self.repaint()

    def closeEnough(self, p1, p2):
        #d = distance(p1 - p2)
        #m = (p1-p2).manhattanLength()
        #print "d %.2f, m %d, %.2f" % (d, m, d - m)
        return distance(p1 - p2) < self.epsilon



def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())

