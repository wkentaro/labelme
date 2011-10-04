#!/usr/bin/python
# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

class Shape(object):

    def __init__(self, label=None,
            line_color=QColor(0, 255, 0, 128),
            fill_color=QColor(255, 0, 0, 128)):

        self.label = label
        self.line_color = line_color
        self.fill_color = fill_color
	self.pointSize=8 # draw square around each point , with length and width =8 pixels
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

    def paint(self, painter):
        if self.points:
            pen = QPen(self.line_color)
            painter.setPen(pen)
            path = QPainterPath()
            pathRect = QPainterPath()

            path.moveTo(self.points[0].x(), self.points[0].y())
            pathRect.addRect( self.points[0].x()-self.pointSize/2, self.points[0].y()-self.pointSize/2, self.pointSize,self.pointSize)

            for p in self.points[1:]:
                path.lineTo(p.x(), p.y())
		pathRect.addRect(p.x()-self.pointSize/2. ,p.y()-self.pointSize/2,self.pointSize,self.pointSize)
            painter.drawPath(path)
            #painter.drawPath(pathRect)


            if self.fill:
                painter.fillPath(path, self.fill_color)

	painter.fillPath(pathRect, self.line_color)



    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value

