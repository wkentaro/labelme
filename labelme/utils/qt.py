import os.path as osp
from math import sqrt

import numpy as np
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

here = osp.dirname(osp.abspath(__file__))


def newIcon(icon_file_name: str) -> QtGui.QIcon:
    if osp.splitext(icon_file_name)[1] == "":
        icon_file_name = f"{icon_file_name}.png"  # XXX: convention
    icons_dir: str = osp.join(here, "../icons")
    return QtGui.QIcon(osp.join(":/", icons_dir, icon_file_name))


def newButton(text, icon=None, slot=None):
    b = QtWidgets.QPushButton(text)
    if icon is not None:
        b.setIcon(newIcon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b


def newAction(
    parent,
    text,
    slot=None,
    shortcut=None,
    icon=None,
    tip=None,
    checkable=False,
    enabled=True,
    checked=False,
):
    """Create a new action and assign callbacks, shortcuts, etc."""
    a = QtWidgets.QAction(text, parent)
    if icon is not None:
        a.setIconText(text.replace(" ", "\n"))
        a.setIcon(newIcon(icon))
    if shortcut is not None:
        if isinstance(shortcut, list | tuple):
            a.setShortcuts(shortcut)
        else:
            a.setShortcut(shortcut)
    if tip is not None:
        a.setToolTip(tip)
        a.setStatusTip(tip)
    if slot is not None:
        a.triggered.connect(slot)
    if checkable:
        a.setCheckable(True)
    a.setEnabled(enabled)
    a.setChecked(checked)
    return a


def addActions(widget, actions):
    for action in actions:
        if action is None:
            widget.addSeparator()
        elif isinstance(action, QtWidgets.QMenu):
            widget.addMenu(action)
        else:
            widget.addAction(action)


def labelValidator():
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)


def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())


def distancetoline(point, line):
    p1, p2 = line
    p1 = np.array([p1.x(), p1.y()])
    p2 = np.array([p2.x(), p2.y()])
    p3 = np.array([point.x(), point.y()])
    if np.dot((p3 - p1), (p2 - p1)) < 0:
        return np.linalg.norm(p3 - p1)
    if np.dot((p3 - p2), (p1 - p2)) < 0:
        return np.linalg.norm(p3 - p2)
    if np.linalg.norm(p2 - p1) == 0:
        return np.linalg.norm(p3 - p1)
    return np.linalg.norm(np.cross(p2 - p1, p1 - p3)) / np.linalg.norm(p2 - p1)


def fmtShortcut(text):
    mod, key = text.split("+", 1)
    return f"<b>{mod}</b>+<b>{key}</b>"


def angleRad(p1: QtCore.QPointF, p2: QtCore.QPointF, flip_y = False):
    p = p2 - p1
    return np.atan2(p.y() if flip_y == False else -p.y(), p.x())


def rectangleFourthPoint(p1: QtCore.QPointF, p2: QtCore.QPointF, p3: QtCore.QPointF) -> QtCore.QPointF:
    return p3 + p1 - p2


def projectPointAtRightAngle(p1: QtCore.QPointF, p2: QtCore.QPointF, p3: QtCore.QPointF) -> QtCore.QPointF:
    """
    Find a new p3, such that the line 'p2 -> p3' forms a 90 degree angle with 'p2 -> p1'.
    """
    target_vec = np.array([p1.y() - p2.y(), -(p1.x() - p2.x())]) # Vector perpendicular from 'p2 -> p1'.
    source_vec = np.array([p3.x() - p2.x(), p3.y() - p2.y()]) # Vector 'p2 -> p3'.
    offset_from_p2 = target_vec * np.dot(target_vec, source_vec) / np.dot(target_vec, target_vec)
    projected_p3 = np.array([p2.x(), p2.y()]) + offset_from_p2
    return QtCore.QPointF(*projected_p3)


def projectPointOnLine(p1: QtCore.QPointF, p2: QtCore.QPointF, p3: QtCore.QPointF) -> QtCore.QPointF:
    """
    Find a new p3 projected along the 'p1 -> p2' line.
    """
    target_vec = np.array([p1.x() - p2.x(), p1.y() - p2.y()]) # Vector 'p1 -> p2'.
    source_vec = np.array([p3.x() - p2.x(), p3.y() - p2.y()]) # Vector 'p2 -> p3'.
    offset_from_p2 = target_vec * np.dot(target_vec, source_vec) / np.dot(target_vec, target_vec)
    projected_p3 = np.array([p2.x(), p2.y()]) + offset_from_p2
    return QtCore.QPointF(*projected_p3)


def rotate(point: np.ndarray | list, angle_rad: float):
    """
    Rotate a point around (0,0).
    """
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    rotation_mat = np.array([[c, -s], [s, c]])
    return np.matmul(rotation_mat, np.transpose(point))


def rotateMany(points, angle_deg: float):
    """
    Rotate a list of points around (0,0).
    """
    output = []
    for p in points:
        output.append(rotate(p, angle_deg))
    return output