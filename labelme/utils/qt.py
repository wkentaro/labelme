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


def newIcon(icon_file_name: str) -> QtGui.QIcon:
    if Path(icon_file_name).suffix == "":
        icon_file_name = f"{icon_file_name}.png"  # XXX: convention
    return QtGui.QIcon(str(here.parent / "icons" / icon_file_name))


def newButton(
    text: str,
    icon: str | None = None,
    slot: Callable[..., object] | None = None,
) -> QtWidgets.QPushButton:
    b = QtWidgets.QPushButton(text)
    if icon is not None:
        b.setIcon(newIcon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b


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


def addActions(
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


def labelValidator() -> QtGui.QRegExpValidator:
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)


def distance(p: QtCore.QPointF) -> float:
    return sqrt(p.x() * p.x() + p.y() * p.y())


def distancetoline(
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


def fmtShortcut(text: str) -> str:
    mod, key = text.split("+", 1)
    return f"<b>{mod}</b>+<b>{key}</b>"


def angleRad(p1: QtCore.QPointF, p2: QtCore.QPointF, *, flip_y: bool = False) -> float:
    delta = p2 - p1
    y = -delta.y() if flip_y else delta.y()
    return float(np.arctan2(y, delta.x()))


def _project_point_along_direction(
    base: QtCore.QPointF, direction: np.ndarray, point: QtCore.QPointF
) -> QtCore.QPointF:
    denominator = float(np.dot(direction, direction))
    if denominator == 0.0:
        return QtCore.QPointF(point)
    base_to_point = np.array([point.x() - base.x(), point.y() - base.y()])
    offset = direction * (np.dot(direction, base_to_point) / denominator)
    return QtCore.QPointF(float(base.x() + offset[0]), float(base.y() + offset[1]))


def projectPointAtRightAngle(
    p1: QtCore.QPointF,
    p2: QtCore.QPointF,
    p3: QtCore.QPointF,
) -> QtCore.QPointF:
    """Project p3 onto the line through p2 perpendicular to (p2 -> p1)."""
    perpendicular = np.array([p1.y() - p2.y(), -(p1.x() - p2.x())])
    return _project_point_along_direction(base=p2, direction=perpendicular, point=p3)


def projectPointOnLine(
    p1: QtCore.QPointF,
    p2: QtCore.QPointF,
    p3: QtCore.QPointF,
) -> QtCore.QPointF:
    direction = np.array([p1.x() - p2.x(), p1.y() - p2.y()])
    return _project_point_along_direction(base=p2, direction=direction, point=p3)
