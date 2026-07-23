from __future__ import annotations

import numpy as np
import pytest
from PySide6 import QtGui

from labelme._shape import Shape
from labelme._shape import ShapeType
from labelme._widgets._shape_render import Palette
from labelme._widgets._shape_render import ShapeRenderContext
from labelme._widgets._shape_render import bounds
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


def _shape(
    shape_type: ShapeType, points: list[list[float]], *, closed: bool = False
) -> Shape:
    return Shape(
        label="a",
        shape_type=shape_type,
        points=np.array(points, dtype=np.float64),
        closed=closed,
    )


@pytest.mark.parametrize(
    ("shape_type", "points", "closed", "expected"),
    [
        ("rectangle", [[10, 10], [50, 30]], False, (10.0, 10.0, 40.0, 20.0)),
        # radius = ||(3, 4)|| = 5, so the box is the point (0, 0) inflated by 5.
        ("circle", [[0, 0], [3, 4]], False, (-5.0, -5.0, 10.0, 10.0)),
        (
            "oriented_rectangle",
            [[0, 0], [10, 0], [10, 5], [0, 5]],
            False,
            (0.0, 0.0, 10.0, 5.0),
        ),
        ("polygon", [[0, 0], [10, 0], [10, 5], [0, 5]], True, (0.0, 0.0, 10.0, 5.0)),
        # A single point bounds to a zero-size rect at its own location.
        ("point", [[100, 100]], False, (100.0, 100.0, 0.0, 0.0)),
    ],
)
def test_bounds_spans_the_shape(
    shape_type: ShapeType,
    points: list[list[float]],
    closed: bool,
    expected: tuple[float, float, float, float],
) -> None:
    shape = _shape(shape_type, points, closed=closed)
    assert bounds(shape=shape).getRect() == expected


@pytest.mark.parametrize(
    # Each shape type guards on its own point count; before that guard is met
    # (mid-draw), bounds must be the null rect rather than crash.
    ("shape_type", "points"),
    [
        ("rectangle", [[5, 5]]),
        ("circle", [[5, 5]]),
        ("oriented_rectangle", [[0, 0], [10, 0], [10, 5]]),
    ],
)
def test_bounds_is_empty_for_incomplete_shape(
    shape_type: ShapeType, points: list[list[float]]
) -> None:
    shape = _shape(shape_type, points)
    assert bounds(shape=shape).getRect() == (0.0, 0.0, 0.0, 0.0)


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
