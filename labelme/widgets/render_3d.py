# from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg
import pyqtgraph.opengl as gl
import numpy as np
import cv2

class render_3d(gl.GLViewWidget):
    def __init__(self,image:np.ndarray=None) -> None:
        super(gl.GLViewWidget, self).__init__()
        GL_ALPHA_TEST = gl.shaders.GL_ALPHA_TEST
        GL_CULL_FACE = gl.shaders.GL_CULL_FACE
        GL_CULL_FACE_MODE = gl.shaders.GL_CULL_FACE_MODE
        GL_BACK = gl.shaders.GL_BACK
        # gl.shaders.glFrustum
        glBlendFunc = gl.shaders.glBlendFunc
        GL_SRC_ALPHA = gl.shaders.GL_SRC_ALPHA
        GL_ONE_MINUS_SRC_ALPHA = gl.shaders.GL_ONE_MINUS_SRC_ALPHA
        self.image = image
        if not image is None:
            self.preproc_img()


def draw_SurfacePlot(z_vals):
    
    Plot = gl.GLSurfacePlotItem(z=z_vals,
                        shader='shaded',
                        computeNormals=True,
                        glOptions='opaque',
                        smooth=True,
                        )
    Plot.scale(16./49., 16./49., 15)
    Plot.translate(-500, -200, 0)
    return Plot

def draw_grid(scale):
    grid = gl.GLGridItem()
    grid.scale(100,100,0.1)
    grid.setDepthValue(20)  # draw grid after surfaces since they may be translucent
    return grid