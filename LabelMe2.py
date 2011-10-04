#!/usr/bin/env python


import re
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import ui_LabelME
from shape import *

MAC = "qt_mac_set_native_menubar" in dir()


class LabelMeWindow(QMainWindow,
        ui_LabelME.Ui_MainWindow):

    def __init__(self, text, parent=None):
        super(LabelMeWindow, self).__init__(parent)
        self.__text = unicode(text)
        self.__index = 0
        
        self.pic=QPixmap()
        t=self.pic.load('me2.jpg')
        self.shapes=[]
        self.counter=0
        sp=shape('one',QColor(0,255,0))
        self.shapes.append(sp)
        
        self.setupUi(self)
        self.dockWidget.setVisible(False)
        
    def text(self):

        return self.__text


    def paintEvent(self, event):

       for shape in self.shapes:
        	qpt = QPainter()
        	qpt.begin(self)
       	 	shape.drawShape(qpt)
       	 	qpt.end()
        
           
    
  
            
   
        
        
    def mousePressEvent(self, ev):
        index=self.counter
        if ev.button()==1:
        
        	self.shapes[index].addPoint(ev.pos())
        if ev.button()==2:
        	self.shapes[index].setFill(True)
        	self.counter=index+1
        	self.shapes.append(shape('one',QColor(0,255,0)))
        	
        self.repaint()


if __name__ == "__main__":
    import sys

    text = "text"

    

    app = QApplication(sys.argv)
    form = LabelMeWindow(text)
    
    form.show()
    app.exec_()

