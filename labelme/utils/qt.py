from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
from math import sqrt
from pathlib import Path
from typing import Final

import numpy as np
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

here = Path(__file__).resolve().parent


def new_icon(icon_file_name: str) -> QtGui.QIcon:
    ICON_SUFFIX: Final[str] = ".png"
    icon_path = here.parent / "icons" / icon_file_name
    if icon_path.suffix == "":
        icon_path = icon_path.with_suffix(ICON_SUFFIX)
    return QtGui.QIcon(str(icon_path))


def new_button(
    text: str,
    icon: str | None = None,
    slot: Callable[..., object] | None = None,
) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    if icon is not None:
        button.setIcon(new_icon(icon))
    if slot is not None:
        button.clicked.connect(slot)
    return button


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
    action = QtWidgets.QAction(text, parent)
    if icon is not None:
        action.setIconText(text.replace(" ", "\n"))
        action.setIcon(new_icon(icon))
    if isinstance(shortcut, list | tuple):
        action.setShortcuts(shortcut)
    elif shortcut is not None:
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


def add_actions(
    widget: QtWidgets.QMenu | QtWidgets.QToolBar,
    actions: Sequence[QtWidgets.QAction | QtWidgets.QMenu | None],
) -> None:
    for entry in actions:
        if entry is None:
            widget.addSeparator()
            continue
        if isinstance(entry, QtWidgets.QMenu):
            widget.addMenu(entry)  # ty: ignore[unresolved-attribute]
            continue
        widget.addAction(entry)


def label_validator() -> QtGui.QRegExpValidator:
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)


def distance(p: QtCore.QPointF) -> float:
    return sqrt(p.x() * p.x() + p.y() * p.y())


def distance_to_line(
    point: QtCore.QPointF,
    line: tuple[QtCore.QPointF, QtCore.QPointF],
) -> float:
    start, end = line
    sx, sy = start.x(), start.y()
    ex, ey = end.x(), end.y()
    px, py = point.x(), point.y()

    edge_x = ex - sx
    edge_y = ey - sy
    length_sq = edge_x * edge_x + edge_y * edge_y
    if length_sq == 0:
        return float(np.hypot(px - sx, py - sy))

    t = ((px - sx) * edge_x + (py - sy) * edge_y) / length_sq
    t = min(1.0, max(0.0, t))

    nearest_x = sx + t * edge_x
    nearest_y = sy + t * edge_y
    return float(np.hypot(px - nearest_x, py - nearest_y))


def shift_pressed() -> bool:
    return bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier)


def format_shortcut(text: str) -> str:
    if "+" not in text:
        raise ValueError(f"shortcut missing '+': {text!r}")
    modifier, _, key = text.partition("+")
    return f"<b>{modifier}</b>+<b>{key}</b>"


def direction_angle(*, start: QtCore.QPointF, end: QtCore.QPointF) -> float:
    delta = end - start
    return float(np.arctan2(delta.y(), delta.x()))


def _project_point_along_direction(
    *,
    base: QtCore.QPointF,
    direction: QtCore.QPointF,
    point: QtCore.QPointF,
) -> QtCore.QPointF:
    length_sq = QtCore.QPointF.dotProduct(direction, direction)
    if length_sq == 0.0:
        return QtCore.QPointF(point)
    t = QtCore.QPointF.dotProduct(direction, point - base) / length_sq
    return base + direction * t


def project_point_on_line(
    *,
    point: QtCore.QPointF,
    line_start: QtCore.QPointF,
    line_end: QtCore.QPointF,
) -> QtCore.QPointF:
    return _project_point_along_direction(
        base=line_end, direction=line_start - line_end, point=point
    )


def project_point_on_perpendicular_line(
    *,
    point: QtCore.QPointF,
    line_start: QtCore.QPointF,
    line_end: QtCore.QPointF,
) -> QtCore.QPointF:
    delta = line_start - line_end
    return _project_point_along_direction(
        base=line_end,
        direction=QtCore.QPointF(delta.y(), -delta.x()),
        point=point,
    )
