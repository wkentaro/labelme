import os.path as osp

import numpy as np
from numpy.linalg import norm
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets


here = osp.dirname(osp.abspath(__file__))


def new_icon(icon):
    icons_dir = osp.join(here, "../icons")
    return QtGui.QIcon(osp.join(":/", icons_dir, "%s.png" % icon))


def new_button(text, icon=None, slot=None):
    b = QtWidgets.QPushButton(text)
    if icon is not None:
        b.setIcon(new_icon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b


def new_action(
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
    action = QtWidgets.QAction(text, parent)
    if icon is not None:
        action.setIconText(text.replace(" ", "\n"))
        action.setIcon(new_icon(icon))
    if shortcut is not None:
        if isinstance(shortcut, (list, tuple)):
            action.setShortcuts(shortcut)
        else:
            action.setShortcut(shortcut)
    if tip is not None:
        action.setToolTip(tip)
        action.setStatusTip(tip)
    if slot is not None:
        action.triggered.connect(slot)
    if checkable:
        action.setCheckable(True)
    action.setEnabled(enabled)
    action.setChecked(checked)
    return action


def add_actions(widget, actions):
    for action in actions:
        if action is None:
            widget.addSeparator()
        elif isinstance(action, QtWidgets.QMenu):
            widget.addMenu(action)
        else:
            widget.addAction(action)


def labelValidator():
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)


class struct(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def distance(p):
    return norm(np.array([p.x(), p.y()]).astype(np.uint16))


def distancetoline(point, line: np.ndarray):
    p1, p2 = line

    p3 = np.array([[point.x(), point.y()]])

    if np.dot((p3 - p1), (p2 - p1)) < 0:
        return np.linalg.norm(p3 - p1)
    if np.dot((p3 - p2), (p1 - p2)) < 0:
        return np.linalg.norm(p3 - p2)
    if np.linalg.norm(p2 - p1) == 0:
        return 0
    return np.linalg.norm(np.cross(np.subtract(p2, p1),
                          np.subtract(p1, p3))) / np.linalg.norm(p2 - p1)


def fmtShortcut(text):
    mod, key = text.split("+", 1)
    return "<b>%s</b>+<b>%s</b>" % (mod, key)
