import math
from qtpy import QtCore


class RotateRectangle(object):
    def __init__(self):
        self.rect = None
        self.angle = 0

    def printSelf(self):
        print("rect", self.rect)
        print("angle", self.angle)

    def outOfPixmap(self, pixmap, points):
        w, h = pixmap.width(), pixmap.height()
        for p in points:
            if not (0 <= p.x() <= w - 1 and 0 <= p.y() <= h - 1):
                return True
        return False

    def clone(self):
        new = RotateRectangle()
        new.angle = self.angle
        new.rect = self.rect
        return new

    def createFromLine(self, pt1, pt2):
        x1, y1 = pt1.x(), pt1.y()
        x2, y2 = pt2.x(), pt2.y()
        self.rect = [
            QtCore.QPointF(x1, y1),
            QtCore.QPointF(x1, y2),
            QtCore.QPointF(x2, y2),
            QtCore.QPointF(x2, y1),
        ]
        self.angle = 0

    def createFromPoint(self, points):
        x2, y2 = points[1].x(), points[1].y()
        x3, y3 = points[2].x(), points[2].y()
        angle = math.degrees(math.atan2(y3 - y2, x3 - x2))
        cx = sum([point.x() for point in points]) / 4
        cy = sum([point.y() for point in points]) / 4
        self.rect = []
        for point in points:
            x_rotated, y_rotated = self.rotatePoint(
                point.x(), point.y(), cx, cy, -angle
            )
            self.rect.append(QtCore.QPointF(x_rotated, y_rotated))
        self.angle = angle

    def getSideLength(self, side):
        return math.sqrt(
            (side[1][0] - side[0][0]) ** 2 + (side[1][1] - side[0][1]) ** 2
        )

    def rotatePoint(self, x, y, a, b, angle):
        angle = math.radians(angle)
        ox = x - a
        oy = y - b
        nx = ox * math.cos(angle) - oy * math.sin(angle) + a
        ny = ox * math.sin(angle) + oy * math.cos(angle) + b
        return (nx, ny)

    def cx(self):
        return sum([point.x() for point in self.rect]) / 4

    def cy(self):
        return sum([point.y() for point in self.rect]) / 4

    def getPoints(self):
        points = self.rotatePoints(self.angle)
        return points

    def rotatePoints(self, angle):
        assert len(self.rect) == 4
        points_ = []
        for p in self.rect:
            x_rotated, y_rotated = self.rotatePoint(
                p.x(), p.y(), self.cx(), self.cy(), angle
            )
            points_.append(QtCore.QPointF(x_rotated, y_rotated))
        return points_

    def moveVertexBy(self, points, i, offset, pixmap):
        if i not in range(4):
            raise ValueError(
                "The vertex index value of the rotated rectangle must be between [0, 3]"
            )
        # print("this:")
        # self.printSelf()
        back = self.rect
        prev = (i - 1) % 4
        next = (i + 1) % 4
        diagonal = (i + 2) % 4
        if i == 0 or i == 2:
            prev_value = self.rect[prev] + QtCore.QPointF(0, offset.y())
            next_value = self.rect[next] + QtCore.QPointF(offset.x(), 0)
            reverse_x = offset.x() > 0 if i == 0 else offset.x() < 0
            reverse_y = offset.y() > 0 if i == 0 else offset.y() < 0
            if reverse_y and abs(offset.y()) > abs(
                self.rect[next].y() - self.rect[i].y()
            ):
                return points
            if reverse_x and abs(offset.x()) > abs(
                self.rect[prev].x() - self.rect[i].x()
            ):
                return points
        else:
            prev_value = self.rect[prev] + QtCore.QPointF(offset.x(), 0)
            next_value = self.rect[next] + QtCore.QPointF(0, offset.y())
            reverse_x = offset.x() > 0 if i == 1 else offset.x() < 0
            reverse_y = offset.y() < 0 if i == 1 else offset.y() > 0
            if reverse_x and abs(offset.x()) > abs(
                self.rect[next].x() - self.rect[i].x()
            ):
                return points
            if reverse_y and abs(offset.y()) > abs(
                self.rect[prev].y() - self.rect[i].y()
            ):
                return points
        w = abs(prev_value.x() - next_value.x())
        h = abs(prev_value.y() - next_value.y())
        if 1 >= w or 1 >= h:
            return points
        self.rect[prev] = prev_value
        self.rect[next] = next_value
        self.rect[i] += offset
        rotate_rect = self.getPoints()
        if self.outOfPixmap(pixmap, rotate_rect):
            self.rect = back
            return points
        offset_diagonal = points[diagonal] - rotate_rect[diagonal]
        return [p + offset_diagonal for p in rotate_rect]

    def moveBy(self, offset):
        self.rect = [p + offset for p in self.rect]
