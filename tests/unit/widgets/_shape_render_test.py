from __future__ import annotations

import numpy as np
import pytest
from PySide6 import QtGui

from labelme._shape import Shape
from labelme._widgets._shape_render import Palette
from labelme._widgets._shape_render import ShapeRenderContext
from labelme._widgets._shape_render import bounds
from labelme._widgets._shape_render import is_hit_by_point
from labelme._widgets._shape_render import render_shape

_SIZE = 200


def _polygon(label: str | None) -> Shape:
    return Shape(
        label=label,
        shape_type="polygon",
        points=np.array([[50, 50], [150, 50], [150, 150], [50, 150]], dtype=np.float64),
        closed=True,
    )


def _unit_square_polygon() -> Shape:
    return Shape(
        shape_type="polygon",
        points=np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float64),
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


def _hit(shape: Shape, point: tuple[float, float]) -> bool:
    return is_hit_by_point(
        shape=shape,
        point=np.array(point, dtype=np.float64),
        scale=1.0,
        point_size=8,
        epsilon=5.0,
    )


def test_line_is_hit_near_its_segment() -> None:
    shape = Shape(
        shape_type="line",
        points=np.array([[0, 0], [100, 0]], dtype=np.float64),
    )
    assert _hit(shape, (50, 2)) is True
    assert _hit(shape, (50, 20)) is False


def test_linestrip_hit_ignores_phantom_closing_edge() -> None:
    shape = Shape(
        shape_type="linestrip",
        points=np.array([[0, 0], [100, 0], [100, 100]], dtype=np.float64),
    )
    # Near a real segment (the bottom edge) is a hit.
    assert _hit(shape, (50, 2)) is True
    # The diagonal from the last point back to the first is never drawn, so a
    # click on it must not register as a hit.
    assert _hit(shape, (50, 50)) is False


def test_points_shape_is_never_body_hit() -> None:
    shape = Shape(
        shape_type="points",
        points=np.array([[10, 10], [20, 20]], dtype=np.float64),
    )
    assert _hit(shape, (10, 10)) is False


def test_point_shape_hit_within_radius() -> None:
    shape = Shape(
        shape_type="point",
        points=np.array([[10, 10]], dtype=np.float64),
    )
    # point_size / 2 == 4, so a point 2px away hits and one 10px away misses.
    assert _hit(shape, (10, 12)) is True
    assert _hit(shape, (10, 20)) is False


def test_empty_point_shape_is_not_hit() -> None:
    shape = Shape(shape_type="point")
    assert _hit(shape, (0, 0)) is False


def test_mask_shape_hit_reads_the_translated_pixel() -> None:
    mask = np.zeros((5, 5), dtype=np.bool_)
    mask[2, 3] = True
    shape = Shape(
        shape_type="mask",
        points=np.array([[10, 10], [15, 15]], dtype=np.float64),
        mask=mask,
    )
    # The mask origin is the bbox top-left (10, 10), so mask[2, 3] is at (13, 12).
    assert _hit(shape, (13, 12)) is True
    # Inside the bbox but where the mask is False.
    assert _hit(shape, (11, 11)) is False
    # Outside the mask array bounds is guarded to a miss.
    assert _hit(shape, (5, 5)) is False
    assert _hit(shape, (100, 100)) is False


def test_polygon_hit_uses_path_containment() -> None:
    shape = _unit_square_polygon()
    assert _hit(shape, (5, 5)) is True
    assert _hit(shape, (50, 50)) is False


def test_bounds_returns_the_shape_extent() -> None:
    rect = bounds(shape=_unit_square_polygon())
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (0, 0, 10, 10)
