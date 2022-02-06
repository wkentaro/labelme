from cv2 import line
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Cursor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from qtpy.QtWidgets import QWidget


class Canvas(FigureCanvas):
    def __init__(self, parent) -> None:
        self.fig, self.ax = plt.subplots(constrained_layout=True)
        # fig.tight_layout(rect=[0,0,1,1])
        plt.ion()
        super().__init__(self.fig)
        self.coord = []
        self.setParent(parent)
        t = np.arange(0.0, 2.0, 0.01)
        s = 1 + np.sin(2 * np.pi * t)
        # self.cursor = Cursor(self.ax, horizOn=True, vertOn=True)
        
        self.ax.plot(t, s)
        self.ax.grid()

    def update_plot(self, ylim: list, x_vals: np.ndarray, start: int = 0):
        assert len(ylim) == 2,\
            "ylim must specify upper and lower limit of y axis"
        self.ax.clear()
        self.ax.margins(x=0)
        self.ax.use_sticky_edges = True
        y_range = np.arange(start, start + len(x_vals), 1)
        self.line, = self.ax.plot(y_range, x_vals)
        self.ax.set(xlabel="X Position" , ylabel="Pixel Value", title="Height Plot")
        # self.ax.draw()

    def mousePressEvent(self, ev):
        y = ev.pos().y()
        # invert y
        y = self.height() - y
        fig_shift = self.ax.bbox.size[0] * self.ax.figbox.intervalx[0]
        x = ev.pos().x() - fig_shift
        
        x_pos = len(self.line.get_data()[0]) * x / self.ax.bbox.size[0]
        mapped_x_pos = int(self.line.get_data()[0][0] + x_pos)
        z_val = self.line.get_data()[1][int(x_pos)]

        self.annotation = self.ax.annotate("test",
                                           xy=(10, 10),
                                           xytext=(10, -20),
                                           xycoords="subfigure pixels",
                                           textcoords="offset pixels"
                                           )
       
        self.coord.append((x, y))
        self.cursor = Cursor(self.ax, horizOn=True, vertOn=True, useblit=True)
        self.ax.axvline(mapped_x_pos, color="red")
        self.ax.axhline(z_val, color="red")
        self.annotation.xy = (x - 20, y)
        text = f"{mapped_x_pos},{z_val}"
        self.annotation.set_text(text)
        self.annotation.set_visible(True)
        # self.fig.canvas.draw()