import os.path as osp
from math import sqrt
from typing import Optional
from typing import Union

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


def newButton(
    text: str,
    icon: Optional[str] = None,
    slot=None,
) -> QtWidgets.QPushButton:
    """Create a QPushButton with optional icon and click callback."""
    button = QtWidgets.QPushButton(text)
    if icon is not None:
        button.setIcon(newIcon(icon))
    if slot is not None:
        button.clicked.connect(slot)
    return button


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


def addActions(widget, actions) -> None:
    """Add a list of actions to a widget; None inserts a separator."""
    for action in actions:
        if action is None:
            widget.addSeparator()
        elif isinstance(action, QtWidgets.QMenu):
            widget.addMenu(action)
        else:
            widget.addAction(action)


def labelValidator() -> QtGui.QRegExpValidator:
    """Return a validator that rejects labels starting with whitespace."""
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)


def distance(p: QtCore.QPointF) -> float:
    """Return the Euclidean distance from the origin to point p."""
    return sqrt(p.x() * p.x() + p.y() * p.y())


def distancetoline(
    point: QtCore.QPointF,
    line: list,
) -> float:
    """Return the shortest distance from point to a line segment.

    If the perpendicular projection falls outside the segment, the
    distance to the nearest endpoint is returned instead.
    """
    p1, p2 = line
    a = np.array([p1.x(), p1.y()])
    b = np.array([p2.x(), p2.y()])
    p = np.array([point.x(), point.y()])
    if np.dot((p - a), (b - a)) < 0:
        return np.linalg.norm(p - a)
    if np.dot((p - b), (a - b)) < 0:
        return np.linalg.norm(p - b)
    d = b - a
    if np.linalg.norm(d) == 0:
        return np.linalg.norm(p - a)
    v = a - p
    cross = d[0] * v[1] - d[1] * v[0]
    return abs(cross) / np.linalg.norm(d)


def fmtShortcut(text: str) -> str:
    """Format a shortcut string like 'Ctrl+S' as bold HTML."""
    mod, key = text.split("+", 1)
    return f"<b>{mod}</b>+<b>{key}</b>"
