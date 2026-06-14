from __future__ import annotations

import numpy as np
import pytest
from PySide6 import QtGui

from labelme._shape import Shape
from labelme.widgets._shape_render import Palette
from labelme.widgets._shape_render import ShapeRenderContext
from labelme.widgets._shape_render import render_shape

_SIZE = 200


def _polygon(label: str | None) -> Shape:
    return Shape(
        label=label,
        shape_type="polygon",
        points=np.array([[50, 50], [150, 50], [150, 150], [50, 150]], dtype=np.float64),
        closed=True,
    )


def _render(shape: Shape, *, show_label: bool, scale: float = 1.0) -> QtGui.QImage:
    image = QtGui.QImage(_SIZE, _SIZE, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor(255, 255, 255))
    painter = QtGui.QPainter(image)
    context = ShapeRenderContext(
        scale=scale,
        palette=Palette.from_rgb(rgb=(255, 0, 0)),
        point_size=8,
        point_type="round",
        selected=False,
        fill=False,
        highlight=None,
        rotation_highlight=None,
        show_label=show_label,
    )
    render_shape(painter=painter, shape=shape, context=context)
    painter.end()
    return image


def _diff_rows(a: QtGui.QImage, b: QtGui.QImage, *, bottom: int) -> int:
    # Only the label text differs between renders; everything else (outline,
    # vertices) is identical, so the per-pixel diff isolates the text. Restrict
    # to rows above the shape top edge to assert the text is anchored there.
    count = 0
    for y in range(bottom):
        for x in range(a.width()):
            if a.pixelColor(x, y) != b.pixelColor(x, y):
                count += 1
    return count


@pytest.mark.gui
def test_show_labels_draws_text_above_shape(qapp: QtGui.QGuiApplication) -> None:
    shape = _polygon(label="car")
    # The polygon top edge sits at y=50, so the label text lands above it.
    assert (
        _diff_rows(
            _render(shape, show_label=True),
            _render(shape, show_label=False),
            bottom=48,
        )
        > 0
    )


@pytest.mark.gui
def test_empty_label_draws_no_text(qapp: QtGui.QGuiApplication) -> None:
    for label in (None, ""):
        shape = _polygon(label=label)
        assert (
            _diff_rows(
                _render(shape, show_label=True),
                _render(shape, show_label=False),
                bottom=_SIZE,
            )
            == 0
        )


@pytest.mark.gui
def test_point_shape_label_is_drawn(qapp: QtGui.QGuiApplication) -> None:
    # A single-point shape has a degenerate bounding box; the label must still
    # render (anchored at the point itself).
    shape = Shape(
        label="car",
        shape_type="point",
        points=np.array([[100, 100]], dtype=np.float64),
    )
    assert (
        _diff_rows(
            _render(shape, show_label=True),
            _render(shape, show_label=False),
            bottom=_SIZE,
        )
        > 0
    )


@pytest.mark.gui
def test_label_anchor_tracks_scale(qapp: QtGui.QGuiApplication) -> None:
    shape = _polygon(label="car")
    # At scale 0.5 the shape top moves from y=50 to y=25, so the label follows
    # into the band above y=24 rather than staying near y=48.
    assert (
        _diff_rows(
            _render(shape, show_label=True, scale=0.5),
            _render(shape, show_label=False, scale=0.5),
            bottom=24,
        )
        > 0
    )
