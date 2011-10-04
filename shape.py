#!/usr/bin/python
# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

class shape(object):

    def __init__(self ,label,color):
        self.label=label
        self.points=[]
        self.color=color
        self.fill=False

    def getLabel(self):
        return label

    def setLabel(self,label):
        self.label=label

    def setFill(self,fillB):
        self.fill=fillB

    def addPoint(self,point):
        self.points.append(point)

    def drawShape(self,painter):

        if len(self.points) >0 :
            pen=QPen(self.color)
            painter.setPen(pen)
            prePoint=self.points[0]
            path=QPainterPath()
            path.moveTo(prePoint.x(),prePoint.y())
            for point in self.points:
                path.lineTo(point.x(),point.y())
            painter.drawPath(path)
        if self.fill:
            painter.fillPath(path,Qt.red)
