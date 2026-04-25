from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
from math import sqrt
from pathlib import Path
from typing import Any

import numpy as np
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

here = Path(__file__).resolve().parent


def new_icon(icon_file_name: str) -> QtGui.QIcon:
    if Path(icon_file_name).suffix == "":
        icon_file_name = f"{icon_file_name}.png"  # XXX: convention
    return QtGui.QIcon(str(here.parent / "icons" / icon_file_name))


def new_button(
    text: str,
    icon: str | None = None,
    slot: Callable[..., object] | None = None,
) -> QtWidgets.QPushButton:
    b = QtWidgets.QPushButton(text)
    if icon is not None:
        b.setIcon(new_icon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b


def new_action(
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
    """Create a new action and assign callbacks, shortcuts, etc."""
    a = QtWidgets.QAction(text, parent)
    if icon is not None:
        a.setIconText(text.replace(" ", "\n"))
        a.setIcon(new_icon(icon))
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


def add_actions(
    widget: QtWidgets.QMenu | QtWidgets.QToolBar,
    actions: Sequence[QtWidgets.QAction | QtWidgets.QMenu | None],
) -> None:
    for action in actions:
        if action is None:
            widget.addSeparator()
        elif isinstance(action, QtWidgets.QMenu):
            widget.addMenu(action)  # ty: ignore[unresolved-attribute]
        else:
            widget.addAction(action)


def label_validator() -> QtGui.QRegExpValidator:
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)


def distance(p: QtCore.QPointF) -> float:
    return sqrt(p.x() * p.x() + p.y() * p.y())


def distance_to_line(
    point: QtCore.QPointF,
    line: tuple[QtCore.QPointF, QtCore.QPointF],
) -> np.floating[Any]:
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


def format_shortcut(text: str) -> str:
    mod, key = text.split("+", 1)
    return f"<b>{mod}</b>+<b>{key}</b>"
