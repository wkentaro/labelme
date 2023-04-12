import numpy as np

class Prompt(object):
    def __init__(self):
        self._points = np.array([], dtype=np.float)
        self._labels = np.array([], dtype=np.float)
        self._box = np.array([], dtype=np.float)
        self._mask = np.array([], dtype=np.float)

    def add_point(self, point, label):
        self._points = np.append(self._points, point)
        self._labels = np.append(self._labels, label)

    @property
    def points(self):
        return self._points

    @property
    def labels(self):
        return self._labels

    @property
    def box(self):
        return self._box

    @property
    def mask(self):
        return self._mask

    def empty(self):
        if len(self._points) == 0 and len(self._labels) == 0 and len(self._box) == 0 and len(self._mask) == 0:
            return True
        else:
            return False

