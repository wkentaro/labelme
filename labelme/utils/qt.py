import os.path as osp
from math import sqrt
from collections.abc import Callable

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
    icon: str | None = None,
    slot: Callable | None = None,
) -> QtWidgets.QPushButton:
    b = QtWidgets.QPushButton(text)
    if icon is not None:
        b.setIcon(newIcon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b


def newAction(
    parent: QtCore.QObject,
    text: str,
    slot: Callable | None = None,
    shortcut=None,
    icon: str | None = None,
    tip: str | None = None,
    checkable: bool = False,
    enabled: bool = True,
    checked: bool = False,
) -> QtWidgets.QAction:
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


def addActions(widget: QtWidgets.QWidget, actions) -> None:
    for action in actions:
        if action is None:
            widget.addSeparator()
        elif isinstance(action, QtWidgets.QMenu):
            widget.addMenu(action)
        else:
            widget.addAction(action)


def labelValidator() -> QtGui.QRegExpValidator:
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)


def distance(p: QtCore.QPointF) -> float:
    return sqrt(p.x() * p.x() + p.y() * p.y())


def distancetoline(point: QtCore.QPointF, line: list) -> float:
    p1, p2 = line
    p1 = np.array([p1.x(), p1.y()])
    p2 = np.array([p2.x(), p2.y()])
    p3 = np.array([point.x(), point.y()])
    if np.dot((p3 - p1), (p2 - p1)) < 0:
        return np.linalg.norm(p3 - p1)
    if np.dot((p3 - p2), (p1 - p2)) < 0:
        return np.linalg.norm(p3 - p2)
    d = p2 - p1
    if np.linalg.norm(d) == 0:
        return np.linalg.norm(p3 - p1)
    v = p1 - p3
    cross = d[0] * v[1] - d[1] * v[0]
    return abs(cross) / np.linalg.norm(d)


def fmtShortcut(text: str) -> str:
    mod, key = text.split("+", 1)
    return f"<b>{mod}</b>+<b>{key}</b>"
