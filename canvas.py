
from math import sqrt

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from shape import Shape

class Canvas(QWidget):
    epsilon = 9.0 # TODO: Tune value

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        self.shapes = []
        self.current = None
        self.line_color = QColor(0, 0, 255)
        self.line = Shape(line_color=self.line_color)
        self.scale = 1.0
        self.pixmap = None

        self.setFocusPolicy(Qt.WheelFocus)

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        # Don't allow the user to draw outside the image area.
        # FIXME: When making fast mouse movements, there is not enough
        # spatial resolution to leave the cursor at the edge of the
        # picture. We should probably place the line at the projected
        # position here...
        pos = self.transformPos(ev.posF())
        if self.outOfPixmap(pos):
            return ev.ignore()
        if self.current:
            if len(self.current) > 1 and self.closeEnough(pos, self.current[0]):
                self.line[1] = self.current[0]
                self.line.line_color = self.current.line_color
            else:
                self.line[1] = pos
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
                pos = self.transformPos(ev.posF())
                self.current = Shape()
                self.line.points = [pos, pos]
                self.current.addPoint(pos)
                self.setMouseTracking(True)

    def mouseDoubleClickEvent(self, ev):
        if self.current:
            # Add first point in the list so that it is consistent
            # with shapes created the normal way.
            self.current.addPoint(self.current[0])
            self.finalise()

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

def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())

