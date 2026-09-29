from __future__ import annotations

import dataclasses
from typing import Literal
from unittest.mock import patch

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6.QtWidgets import QApplication

from labelme._shape import Shape
from labelme._widgets import _shape_render
from labelme._widgets._shape_render import Palette
from labelme._widgets._shape_render import ShapeRenderContext
from labelme._widgets._shape_render import VertexHighlight


def _paint_combined_vertices(
    *,
    painter: QtGui.QPainter,
    vertices: list[tuple[QtCore.QRectF, str]],
    fill: QtGui.QColor,
) -> None:
    path = QtGui.QPainterPath()
    for rect, point_type in vertices:
        if point_type == "round":
            path.addEllipse(rect)
        else:
            path.addRect(rect)
    painter.drawPath(path)
    painter.fillPath(path, fill)


def _render(*, shape: Shape, context: ShapeRenderContext, ratio: int) -> np.ndarray:
    image = QtGui.QImage(400 * ratio, 400 * ratio, QtGui.QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(ratio)
    image.fill(QtGui.QColor(40, 70, 90))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.translate(0.3, 0.7)
    _shape_render.render_shape(painter=painter, shape=shape, context=context)
    painter.end()
    return np.frombuffer(image.bits(), dtype=np.uint8).copy().reshape(-1, 4).astype(int)


@pytest.mark.parametrize("ratio", [1, 2])
@pytest.mark.parametrize("point_type", ["round", "square"])
@pytest.mark.parametrize(
    "state", ["normal", "selected", "near", "move", "fill", "zoom"]
)
def test_separated_vertex_pixels_match_combined_paths(
    *,
    qapp: QApplication,
    ratio: int,
    point_type: Literal["round", "square"],
    state: Literal["normal", "selected", "near", "move", "fill", "zoom"],
) -> None:
    assert qapp is not None
    shape = Shape(points=np.array([[50, 50], [250, 50], [250, 250]]), closed=True)
    context = ShapeRenderContext(
        scale=1,
        palette=Palette.from_rgb((240, 20, 40)),
        point_size=8,
        point_type=point_type,
        selected=state == "selected",
        fill=state == "fill",
        highlight=VertexHighlight(index=0, mode=state)
        if state in ("near", "move")
        else None,
        rotation_highlight=None,
    )
    if state == "zoom":
        context = dataclasses.replace(context, scale=0.75)
    with patch.object(
        _shape_render, "_paint_filled_vertices", _paint_combined_vertices
    ):
        expected = _render(shape=shape, context=context, ratio=ratio)
    actual = _render(shape=shape, context=context, ratio=ratio)
    assert np.max(np.abs(actual - expected)) <= 1


@pytest.mark.parametrize("ratio", [1, 2])
@pytest.mark.parametrize("state", ["normal", "selected", "near"])
def test_overlapping_vertex_pixels_match_except_antialiased_edges(
    *, qapp: QApplication, ratio: int, state: str
) -> None:
    assert qapp is not None
    theta = np.linspace(0, 2 * np.pi, 300, endpoint=False)
    shape = Shape(
        points=np.c_[150 + 90 * np.cos(theta), 150 + 90 * np.sin(theta)], closed=True
    )
    context = ShapeRenderContext(
        scale=1,
        palette=Palette.from_rgb((240, 20, 40)),
        point_size=8,
        point_type="round",
        selected=state == "selected",
        fill=False,
        highlight=VertexHighlight(index=0, mode="near") if state == "near" else None,
        rotation_highlight=None,
    )
    with patch.object(
        _shape_render, "_paint_filled_vertices", _paint_combined_vertices
    ):
        expected = _render(shape=shape, context=context, ratio=ratio)
    actual = _render(shape=shape, context=context, ratio=ratio)
    # Independent strokes blend overlapping edges separately. Keep at least
    # 99% of this image within one channel value, including the hover pattern.
    difference = np.abs(actual - expected)
    assert np.mean(np.all(difference <= 1, axis=-1)) >= 0.99
