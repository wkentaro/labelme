import numpy as np
import sys
sys.ps1 = 'SOMETHING'
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from qtpy.QtWidgets import QWidget


class Canvas(FigureCanvas):
    def __init__(self, parent) -> None:
        fig, self.ax = plt.subplots()
        fig.tight_layout()
        super().__init__(fig)

        self.setParent(parent)
        t = np.arange(0.0, 2.0, 0.01)
        s = 1 + np.sin(2 * np.pi * t)

        self.ax.plot(t, s)

        
        self.ax.grid()

    def update_plot(self, ylim: list, x_vals: np.ndarray):

        assert len(ylim) == 2,\
            "ylim must specify upper and lower limit of y axis"
        self.ax.clear()
        y_range = np.arange(0, len(x_vals), 1)
        self.ax.plot(y_range, x_vals)
        self.ax.set(xlabel="X Position" , ylabel="Pixel Value", title="Height Plot")

        # self.ax.draw()
        
        
