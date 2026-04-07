from __future__ import annotations

import os.path as osp
from collections.abc import Callable
from collections.abc import Sequence
from math import sqrt
from typing import Any

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
    slot: Callable[..., object] | None = None,
) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    if icon is not None:
        button.setIcon(newIcon(icon))
    if slot is not None:
        button.clicked.connect(slot)
    return button


def newAction(
    parent: QtWidgets.QWidget,
    text: str,
    slot: Callable[..., object] | None = None,
    shortcut: str | list[str] | tuple[str, ...] | None = None,
    icon: str | None = None,
    tip: str | None = None,
    checkable: bool = False,
    enabled: bool = True,
    checked: bool = False,
) -> QtWidgets.QAction:
    act = QtWidgets.QAction(text, parent)
    if icon is not None:
        act.setIconText(text.replace(" ", "\n"))
        act.setIcon(newIcon(icon))
    if shortcut is not None:
        if isinstance(shortcut, list | tuple):
            act.setShortcuts(shortcut)
        else:
            act.setShortcut(shortcut)
    if tip is not None:
        act.setToolTip(tip)
        act.setStatusTip(tip)
    if slot is not None:
        act.triggered.connect(slot)
    if checkable:
        act.setCheckable(True)
    act.setEnabled(enabled)
    act.setChecked(checked)
    return act


def addActions(
    widget: QtWidgets.QMenu | QtWidgets.QToolBar,
    actions: Sequence[QtWidgets.QAction | QtWidgets.QMenu | None],
) -> None:
    for entry in actions:
        if entry is None:
            widget.addSeparator()
        elif isinstance(entry, QtWidgets.QMenu):
            widget.addMenu(entry)  # type: ignore[union-attr]
        else:
            widget.addAction(entry)


def labelValidator() -> QtGui.QRegExpValidator:
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)


def distance(p: QtCore.QPointF) -> float:
    dx, dy = p.x(), p.y()
    return sqrt(dx * dx + dy * dy)


def distancetoline(
    point: QtCore.QPointF,
    line: tuple[QtCore.QPointF, QtCore.QPointF],
) -> np.floating[Any]:
    start, end = line
    a = np.array([start.x(), start.y()])
    b = np.array([end.x(), end.y()])
    pt = np.array([point.x(), point.y()])
    ab = b - a
    if np.dot(pt - a, ab) < 0:
        return np.linalg.norm(pt - a)
    if np.dot(pt - b, a - b) < 0:
        return np.linalg.norm(pt - b)
    ab_len = np.linalg.norm(ab)
    if ab_len == 0:
        return np.linalg.norm(pt - a)
    cross_product = ab[0] * (a[1] - pt[1]) - ab[1] * (a[0] - pt[0])
    return abs(cross_product) / ab_len


def fmtShortcut(text: str) -> str:
    modifier, key = text.split("+", 1)
    return f"<b>{modifier}</b>+<b>{key}</b>"
