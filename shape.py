#!/usr/bin/python
# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

# FIXME:
# - Add support for highlighting vertices.

class Shape(object):
    P_SQUARE, P_ROUND = range(2)

    ## The following class variables influence the drawing
    ## of _all_ shape objects.
    line_color = QColor(0, 255, 0, 128)
    fill_color = QColor(255, 0, 0, 128)
    select_color = QColor(255, 255, 255)
    point_type = P_SQUARE
    point_size = 8
    scale = 1.0

    def __init__(self, label=None, line_color=None):
        self.label = label
        self.points = []
        self.fill = False
        self.selected = False
        if line_color is not None:
            # Override the class line_color attribute
            # with an object attribute. Currently this
            # is used for drawing the pending line a different color.
            self.line_color = line_color

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
            pen = QPen(self.select_color if self.selected else self.line_color)
            # Try using integer sizes for smoother drawing(?)
            pen.setWidth(max(1, int(round(2.0 / self.scale))))
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
        d = self.point_size / self.scale
        if self.point_type == self.P_SQUARE:
            path.addRect(point.x() - d/2, point.y() - d/2, d, d)
        else:
            path.addEllipse(point, d/2.0, d/2.0)

    def containsPoint(self, point):
        path = QPainterPath(QPointF(self.points[0]))
        for p in self.points[1:]:
            path.lineTo(QPointF(p))
        return path.contains(QPointF(point))

    def moveBy(self,dx,dy):
        index=0
        for point in self.points:
           newXPos= point.x()+dx
           newYPos=point.y()+dy
           self.points[index]=QPoint(newXPos,newYPos)
           index +=1
           
    def copy(self):
        shapeCopy=Shape()
        for point in self.points:
            shapeCopy.points.append(point)
            shapeCopy.label=self.label
            shapeCopy.fill = self.fill
            shapeCopy.selected = self.selected
        return shapeCopy
    
    
    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value

