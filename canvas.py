
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from shape import Shape

class Canvas(QLabel):
    done = pyqtSignal()
    epsilon = 7**2 # TODO: Tune value

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        self.points = []
        self.shapes = [Shape('one', QColor(0, 255, 0))]
        self.current_line = Shape('line', QColor(255, 0, 0))

    def mousePressEvent(self, ev):
        if ev.button() != 1:
            return

        if not self.points:
            self.setMouseTracking(True)

        self.points.append(ev.pos())
        self.shapes[0].addPoint(ev.pos())
        if self.isClosed():
            self.done.emit()
            print "Points:", self.points
            self.points = []
            self.shapes[0].setFill(True)
            self.setMouseTracking(False)
        self.repaint()

    def isClosed(self):
        return len(self.points) > 1 and self.closeEnough(self.points[0], self.points[-1])

    def mouseMoveEvent(self, ev):
        self.current_line.points = [self.points[-1], self.pos()]
        self.repaint()
       #print "moving", ev.pos()



    def closeEnough(self, p1, p2):
        def dist(p):
            return p.x() * p.x() + p.y() * p.y()
        print p1, p2
        print abs(dist(p1) - dist(p2)), self.epsilon
        return abs(dist(p1) - dist(p2)) < self.epsilon

    def paintEvent(self, event):
        super(Canvas, self).paintEvent(event)
        for shape in self.shapes:
            qp = QPainter()
            qp.begin(self)
            shape.drawShape(qp)
            self.current_line.drawShape(qp)
            qp.end()

