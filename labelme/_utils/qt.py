from __future__ import annotations

import math
import os
from collections.abc import Callable
from collections.abc import Sequence
from typing import Final

import numpy as np
import numpy.typing as npt
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtSvg
from PySide6 import QtWidgets

_ICONS_DIR: Final = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")


def apply_color_theme(*, theme: str) -> None:
    SCHEME_BY_THEME: Final = {
        "system": QtCore.Qt.ColorScheme.Unknown,
        "light": QtCore.Qt.ColorScheme.Light,
        "dark": QtCore.Qt.ColorScheme.Dark,
    }
    scheme = SCHEME_BY_THEME.get(theme, QtCore.Qt.ColorScheme.Unknown)
    QtGui.QGuiApplication.styleHints().setColorScheme(scheme)


class _TintedSvgIconEngine(QtGui.QIconEngine):
    # Substitutes fill="currentColor" with the palette text color at paint time, so
    # icons re-tint live on a theme change instead of baking a fixed color.
    def __init__(self, *, svg: bytes) -> None:
        super().__init__()
        self._svg = svg
        self._pixmaps: dict[tuple[int, int, str], QtGui.QPixmap] = {}

    @staticmethod
    def _tint_color(*, mode: QtGui.QIcon.Mode) -> QtGui.QColor:
        palette = QtWidgets.QApplication.palette()
        group = (
            QtGui.QPalette.ColorGroup.Disabled
            if mode == QtGui.QIcon.Mode.Disabled
            else QtGui.QPalette.ColorGroup.Normal
        )
        role = (
            QtGui.QPalette.ColorRole.HighlightedText
            if mode == QtGui.QIcon.Mode.Selected
            else QtGui.QPalette.ColorRole.WindowText
        )
        return palette.color(group, role)

    def _tinted_pixmap(
        self, *, size: QtCore.QSize, color: QtGui.QColor
    ) -> QtGui.QPixmap:
        key = (size.width(), size.height(), color.name())
        cached = self._pixmaps.get(key)
        if cached is not None:
            return cached
        svg = self._svg.replace(b"currentColor", color.name().encode())
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg))
        image = QtGui.QImage(size, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        renderer.render(painter, QtCore.QRectF(0, 0, size.width(), size.height()))
        painter.end()
        pixmap = QtGui.QPixmap.fromImage(image)
        self._pixmaps[key] = pixmap
        return pixmap

    def pixmap(
        self, size: QtCore.QSize, mode: QtGui.QIcon.Mode, _state: QtGui.QIcon.State, /
    ) -> QtGui.QPixmap:
        # Copy so neither callers nor Qt's scaledPixmap (which sets a device pixel
        # ratio on the result) mutate the shared cached pixmap.
        cached = self._tinted_pixmap(size=size, color=self._tint_color(mode=mode))
        return QtGui.QPixmap(cached)

    def paint(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRect,
        mode: QtGui.QIcon.Mode,
        _state: QtGui.QIcon.State,
        /,
    ) -> None:
        # Render at device pixels so the icon stays crisp on HiDPI/Retina screens,
        # where rect is in device-independent coordinates. Copy before stamping the
        # ratio so the cached pixmap is not mutated.
        dpr = painter.device().devicePixelRatioF()
        cached = self._tinted_pixmap(
            size=(QtCore.QSizeF(rect.size()) * dpr).toSize(),
            color=self._tint_color(mode=mode),
        )
        pixmap = QtGui.QPixmap(cached)
        pixmap.setDevicePixelRatio(dpr)
        painter.drawPixmap(rect, pixmap)

    def cacheKey(self) -> int:
        return hash(
            (
                self._svg,
                int(self._tint_color(mode=QtGui.QIcon.Mode.Normal).rgba()),
                int(self._tint_color(mode=QtGui.QIcon.Mode.Disabled).rgba()),
                int(self._tint_color(mode=QtGui.QIcon.Mode.Selected).rgba()),
            )
        )

    def clone(self) -> QtGui.QIconEngine:
        return _TintedSvgIconEngine(svg=self._svg)


def new_icon(name: str, /) -> QtGui.QIcon:
    DEFAULT_ICON_SUFFIX: Final = ".png"

    if not os.path.splitext(name)[1]:
        name = name + DEFAULT_ICON_SUFFIX
    path = os.path.join(_ICONS_DIR, name)
    if path.endswith(".svg"):
        with open(path, "rb") as f:
            svg = f.read()
        if b"currentColor" in svg:
            return QtGui.QIcon(_TintedSvgIconEngine(svg=svg))
    return QtGui.QIcon(path)


def new_action(
    parent: QtWidgets.QWidget,
    /,
    *,
    text: str = "",
    slot: Callable[..., object] | None = None,
    shortcut: str | Sequence[str] | None = None,
    icon: str | None = None,
    tip: str | None = None,
    checkable: bool = False,
    enabled: bool = True,
    checked: bool = False,
) -> QtGui.QAction:
    action = QtGui.QAction(new_icon(icon) if icon else QtGui.QIcon(), text, parent)
    keys = [shortcut] if isinstance(shortcut, str) else shortcut or ()
    action.setShortcuts([QtGui.QKeySequence(key) for key in keys])
    action.setToolTip(tip or "")
    action.setStatusTip(tip or "")
    action.setCheckable(checkable)
    action.setChecked(checked)
    action.setEnabled(enabled)
    if icon:
        # Tool buttons show the icon text; stacking words keeps them narrow.
        action.setIconText(text.replace(" ", "\n"))
    if slot:
        action.triggered.connect(slot)
    return action


def new_separator(parent: QtWidgets.QWidget, /) -> QtGui.QAction:
    separator = QtGui.QAction(parent)
    separator.setSeparator(True)
    return separator


def label_validator() -> QtGui.QRegularExpressionValidator:
    # Accepts strings of 2+ chars not starting with space or tab.
    # Single non-whitespace char is Intermediate (handled by regex partial match).
    return QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"[^ \t].+"))


def direction_angle(*, start: npt.ArrayLike, end: npt.ArrayLike) -> float:
    s = np.asarray(start, dtype=float)
    e = np.asarray(end, dtype=float)
    delta = e - s
    return float(math.atan2(delta[1], delta[0]))


def project_point_on_line(
    *,
    point: QtCore.QPointF,
    line_start: QtCore.QPointF,
    line_end: QtCore.QPointF,
) -> QtCore.QPointF:
    dx = line_end.x() - line_start.x()
    dy = line_end.y() - line_start.y()
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return QtCore.QPointF(point)
    t = (
        (point.x() - line_start.x()) * dx + (point.y() - line_start.y()) * dy
    ) / length_sq
    return QtCore.QPointF(line_start.x() + t * dx, line_start.y() + t * dy)


def project_point_on_perpendicular_line(
    *,
    point: QtCore.QPointF,
    line_start: QtCore.QPointF,
    line_end: QtCore.QPointF,
) -> QtCore.QPointF:
    # The perpendicular line passes through line_end and is orthogonal to
    # the vector (line_end - line_start).
    dx = line_end.x() - line_start.x()
    dy = line_end.y() - line_start.y()
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return QtCore.QPointF(point)
    # Direction of the perpendicular: (-dy, dx) (rotate 90 degrees).
    # Project point onto the line through line_end with direction (-dy, dx).
    px = point.x() - line_end.x()
    py = point.y() - line_end.y()
    t = (px * (-dy) + py * dx) / length_sq
    return QtCore.QPointF(line_end.x() + t * (-dy), line_end.y() + t * dx)
