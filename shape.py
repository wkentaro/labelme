#!/usr/bin/python
# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

class Shape(object):
    P_SQUARE, P_ROUND = range(2)

    # These are class variables so that changing them changes ALL shapes!
    point_type = P_SQUARE
    point_size = 8

    def __init__(self, label=None,
            line_color=QColor(0, 255, 0, 128),
            fill_color=QColor(255, 0, 0, 128)):

        self.label = label
        self.line_color = line_color
        self.fill_color = fill_color

        self.points = []
        self.fill = False

    def addPoint(self, point):
        self.points.append(point)

    def popPoint(self):
        if self.points:
            return self.points.pop()
        return None

    def isClosed(self):
        return len(self.points) > 1 and self[0] == self[-1]

    # TODO:
    # The paths could be stored and elements added directly to them.
    def paint(self, painter):
        if self.points:
            pen = QPen(self.line_color)
            painter.setPen(pen)

            line_path = QPainterPath()
            vrtx_path = QPainterPath()

            line_path.moveTo(QPointF(self.points[0]))
            self.drawVertex(vrtx_path, self.points[0])

            for p in self.points[1:]:
                line_path.lineTo(QPointF(p))
                # Skip last element, otherwise its vertex is not filled.
                if p != self.points[0]:
		    self.drawVertex(vrtx_path, p)
            painter.drawPath(line_path)
            painter.fillPath(vrtx_path, self.line_color)
            if self.fill:
                painter.fillPath(line_path, self.fill_color)

    def drawVertex(self, path, point):
        d = self.point_size
        if self.point_type == self.P_SQUARE:
            path.addRect(point.x() - d/2, point.y() - d/2, d, d)
        else:
            path.addEllipse(QPointF(point), d/2.0, d/2.0)

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value

