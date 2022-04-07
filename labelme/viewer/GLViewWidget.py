from pyqtgraph.opengl.GLViewWidget import GLViewWidget
from PyQt5 import QtCore, QtGui, QtWidgets


class cust_GLViewWidget(GLViewWidget):
    """custom Class in order to overwrite the default camera controls"""

    def __init__(self, parent=None, devicePixelRatio=None, rotationMethod='euler'):
        super().__init__(parent, devicePixelRatio, rotationMethod)

    def mouseMoveEvent(self, ev):
        lpos = ev.position() if hasattr(ev, 'position') else ev.localPos()
        diff = lpos - self.mousePos
        self.mousePos = lpos
        if ev.buttons() == QtCore.Qt.MouseButton.LeftButton:
            if (ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
                self.pan(diff.x(), diff.y(), 0, relative='view')
            else:
                self.orbit(-diff.x(), diff.y())
        elif ev.buttons() == QtCore.Qt.MouseButton.RightButton:
            # if (ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            #     self.pan(diff.x(), 0, diff.y(), relative='view-upright')
            # else:
            self.pan(diff.x(), diff.y(), 0, relative='view-upright')
        elif ev.buttons() == QtCore.Qt.MouseButton.MiddleButton:
            self.pan(0, 0, diff.y(), relative='view-upright')
        

    def wheelEvent(self, ev):
        # lpos = ev.position() if hasattr(ev, 'position') else ev.localPos()
        # diff = lpos - self.mousePos
        delta = ev.angleDelta()
        if (ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            # self.opts['fov'] *= 0.999**delta
            self.opts['distance'] *= 0.999**delta.y()
        elif (ev.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier):
            # self.opts['distance'] *= 0.999**delta
            self.pan(delta.y() / 4, 0 , 0, relative='view-upright')
        else:
            self.pan(delta.x() / 4, delta.y(), 0, relative='view-upright')
        self.update()
