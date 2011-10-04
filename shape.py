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

        self.vertices = []
        self.fill = False

    def addVertex(self, vertex):
        self.vertices.append(vertex)

    def popVertex(self):
        if self.vertices:
            return self.vertices.pop()
        return None

    def paint(self, painter):
        if self.vertices:
            pen = QPen(self.line_color)
            painter.setPen(pen)
            path = QPainterPath()
            p0 = self.vertices[0]
            path.moveTo(p0.x(), p0.y())
            for v in self.vertices[1:]:
                path.lineTo(v.x(), v.y())
            painter.drawPath(path)

            if self.fill:
                painter.fillPath(path, self.fill_color)

    def __len__(self):
        return len(self.vertices)

    def __getitem__(self, key):
        return self.vertices[key]

