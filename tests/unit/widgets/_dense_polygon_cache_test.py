from __future__ import annotations

import dataclasses
from unittest.mock import patch

import numpy as np
import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtWidgets import QApplication

from labelme._shape import Shape
from labelme._widgets import _shape_render
from labelme._widgets._shape_render import Palette
from labelme._widgets._shape_render import ShapeRenderContext
from labelme._widgets._shape_render import VertexHighlight


def _render(
    *, shape: Shape, context: ShapeRenderContext, ratio: int, offset: float
) -> np.ndarray:
    image = QtGui.QImage(400, 400, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(QtGui.QColor(40, 70, 90))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.translate(offset, offset)
    _shape_render.render_shape(painter=painter, shape=shape, context=context)
    painter.end()
    return np.frombuffer(image.bits(), dtype=np.uint8).copy().astype(int)


@pytest.mark.parametrize("ratio", [1, 2])
@pytest.mark.parametrize("offset", [0.0, 0.3])
def test_cached_polygon_matches_direct_paint_after_edits(
    *, qapp: QApplication, ratio: int, offset: float
) -> None:
    assert qapp is not None
    QtGui.QPixmapCache.clear()
    theta = np.linspace(0, 2 * np.pi, 300, endpoint=False)
    shape = Shape(
        points=np.c_[75 + 40 * np.cos(theta), 75 + 40 * np.sin(theta)], closed=True
    )
    context = ShapeRenderContext(
        scale=1,
        palette=Palette.from_rgb((240, 20, 40)),
        point_size=8,
        point_type="round",
        selected=False,
        fill=False,
        highlight=None,
        rotation_highlight=None,
    )
    for change in ("initial", "point", "fill", "highlight", "zoom", "color", "closed"):
        if change == "point":
            shape.points[0] += [8, 5]
        elif change == "fill":
            context = dataclasses.replace(context, fill=True)
        elif change == "highlight":
            context = dataclasses.replace(
                context, highlight=VertexHighlight(index=0, mode="move")
            )
        elif change == "zoom":
            context = dataclasses.replace(context, scale=0.75)
        elif change == "color":
            context = dataclasses.replace(
                context, palette=Palette.from_rgb((20, 240, 40))
            )
        elif change == "closed":
            shape.closed = False
        with patch.object(_shape_render, "_paint_cached_polygon", return_value=False):
            expected = _render(shape=shape, context=context, ratio=ratio, offset=offset)
        actual = _render(shape=shape, context=context, ratio=ratio, offset=offset)
        assert np.max(np.abs(actual - expected)) <= 1
        # Deep copies restored by undo must reuse the same drawing.
        with patch.object(
            _shape_render,
            "_paint_shape_points",
            side_effect=AssertionError("cache miss"),
        ):
            repeated = _render(
                shape=shape.copy(), context=context, ratio=ratio, offset=offset
            )
        np.testing.assert_array_equal(actual, repeated)


def test_cached_polygon_matches_paint_in_offset_child(*, qapp: QApplication) -> None:
    assert qapp is not None
    theta = np.linspace(0, 2 * np.pi, 300, endpoint=False)
    shape = Shape(
        points=np.c_[75 + 40 * np.cos(theta), 75 + 40 * np.sin(theta)], closed=True
    )
    context = ShapeRenderContext(
        scale=1,
        palette=Palette.from_rgb((240, 20, 40)),
        point_size=8,
        point_type="round",
        selected=False,
        fill=True,
        highlight=None,
        rotation_highlight=None,
    )

    class PolygonWidget(QtWidgets.QWidget):
        def paintEvent(self, event: QtGui.QPaintEvent, /) -> None:
            del event
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            _shape_render.render_shape(painter=painter, shape=shape, context=context)
            painter.end()

    parent = QtWidgets.QWidget()
    parent.resize(400, 400)
    child = PolygonWidget(parent)
    child.setGeometry(80, 90, 200, 200)
    with patch.object(_shape_render, "_paint_cached_polygon", return_value=False):
        expected = parent.grab().toImage()
    actual = parent.grab().toImage()
    expected_pixels = np.frombuffer(expected.bits(), dtype=np.uint8).astype(int)
    actual_pixels = np.frombuffer(actual.bits(), dtype=np.uint8).astype(int)
    assert np.max(np.abs(actual_pixels - expected_pixels)) <= 1
    parent.close()
