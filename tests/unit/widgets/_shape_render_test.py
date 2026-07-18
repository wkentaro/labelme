from __future__ import annotations

import numpy as np
import pytest
from PySide6 import QtGui

from labelme._shape import Shape
from labelme._widgets._shape_render import Palette
from labelme._widgets._shape_render import ShapeRenderContext
from labelme._widgets._shape_render import render_shape

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


def _mask_shape() -> Shape:
    # A non-square True block at an asymmetric origin, so its x and y centers
    # differ and the test pins the row/col-to-x/y axis mapping (a swap in either
    # the origin offset or the point construction would move the outline off the
    # expected center). The block stays clear of the bbox rect, which for a mask
    # shape is the only other stroke drawn.
    mask = np.zeros((40, 40), dtype=bool)
    mask[12:20, 16:26] = True
    return Shape(
        label=None,
        shape_type="mask",
        points=np.array([[5, 8], [45, 48]], dtype=np.float64),
        mask=mask,
    )


def _outline_center(image: QtGui.QImage) -> tuple[float, float]:
    # Restrict to the central window so the bbox rect at the edges does not
    # contaminate the mask block's outline; the opaque line color isolates the
    # outline from the semi-transparent fill blended over the white canvas.
    xs = []
    ys = []
    for y in range(15, 35):
        for x in range(15, 35):
            c = image.pixelColor(x, y)
            if (c.red(), c.green(), c.blue()) == (255, 0, 0):
                xs.append(x)
                ys.append(y)
    assert xs and ys
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


@pytest.mark.gui
def test_mask_outline_aligns_with_fill(qapp: QtGui.QGuiApplication) -> None:
    # The mask fill is rasterized at the correct position; the contour outline
    # must be centered on that same block, not sit a pixel off from it.
    shape = _mask_shape()
    image = _render(shape, show_label=False)
    outline = _outline_center(image)
    assert shape.mask is not None
    ys, xs = np.nonzero(shape.mask)
    origin = shape.points[0]
    expected = (
        origin[0] + (xs.min() + xs.max()) / 2,
        origin[1] + (ys.min() + ys.max()) / 2,
    )
    assert abs(outline[0] - expected[0]) <= 0.5
    assert abs(outline[1] - expected[1]) <= 0.5


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
