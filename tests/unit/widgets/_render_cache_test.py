from __future__ import annotations

import dataclasses
from unittest.mock import Mock

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtGui

from labelme._shape import Shape
from labelme._widgets import _shape_render as render


def _context() -> render.ShapeRenderContext:
    return render.ShapeRenderContext(
        scale=1.0,
        palette=render.Palette.from_rgb(rgb=(30, 180, 90)),
        point_size=8,
        point_type="round",
        selected=False,
        fill=False,
        highlight=None,
        rotation_highlight=None,
    )


def _mask() -> Shape:
    mask = np.zeros((40, 50), dtype=bool)
    mask[2:35, 3:45] = True
    mask[10:20, 15:30] = False
    return Shape(
        shape_type="mask", points=np.array([[31.2, 24.7], [80.2, 63.7]]), mask=mask
    )


def _paint(
    *,
    shape: Shape,
    context: render.ShapeRenderContext,
    cache: render.ShapeRenderCache | None,
    device_pixel_ratio: int = 1,
    opacity: float = 1.0,
) -> QtGui.QImage:
    image = QtGui.QImage(
        260 * device_pixel_ratio,
        220 * device_pixel_ratio,
        QtGui.QImage.Format.Format_ARGB32,
    )
    image.setDevicePixelRatio(device_pixel_ratio)
    image.fill(QtCore.Qt.GlobalColor.white)
    painter = QtGui.QPainter(image)
    painter.setOpacity(opacity)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    render.render_shape(painter=painter, shape=shape, context=context, cache=cache)
    painter.end()
    return image


@pytest.mark.parametrize("scale", [0.447, 1.0, 2.5])
@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize(
    ("fill_mask", "outline"), [(True, True), (True, False), (False, True)]
)
def test_cached_mask_matches_uncached_pixels(
    *,
    scale: float,
    selected: bool,
    fill_mask: bool,
    outline: bool,
) -> None:
    shape = _mask()
    context = dataclasses.replace(
        _context(), scale=scale, selected=selected, fill_mask=fill_mask, outline=outline
    )
    cache = render.ShapeRenderCache()
    expected = _paint(shape=shape, context=context, cache=None)
    for _ in range(2):
        cache.begin_paint()
        assert _paint(shape=shape, context=context, cache=cache) == expected


def test_mask_reuses_contours_across_copy_move_zoom_and_color(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contours = Mock(wraps=render.find_mask_contours)
    monkeypatch.setattr(render, "find_mask_contours", contours)
    cache = render.ShapeRenderCache()
    shape = _mask()
    context = _context()
    _paint(shape=shape, context=context, cache=cache)
    shape = shape.copy()
    shape.points += 3.2
    context = dataclasses.replace(context, scale=2.5, selected=True)
    _paint(shape=shape, context=context, cache=cache)
    assert contours.call_count == 1
    assert _paint(shape=shape, context=context, cache=cache) == _paint(
        shape=shape, context=context, cache=None
    )
    assert shape.mask is not None
    shape.mask[0, 0] = True
    actual = _paint(shape=shape, context=context, cache=cache)
    assert actual == _paint(shape=shape, context=context, cache=None)
    cache.clear()
    assert not cache._entries
    assert cache._size_bytes == 0


@pytest.mark.parametrize(("fill_mask", "outline"), [(True, False), (False, True)])
def test_only_prepares_requested_mask_asset(
    *,
    fill_mask: bool,
    outline: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contours = Mock(wraps=render.find_mask_contours)
    monkeypatch.setattr(render, "find_mask_contours", contours)
    cache = render.ShapeRenderCache()
    _paint(
        shape=_mask(),
        context=dataclasses.replace(_context(), fill_mask=fill_mask, outline=outline),
        cache=cache,
    )
    assert contours.call_count == int(outline)
    assert len(cache._entries) == 1
    value, _ = next(iter(cache._entries.values()))
    assert isinstance(value, QtGui.QImage if fill_mask else QtGui.QPainterPath)


def test_over_budget_scene_reuses_resident_subset(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contours = Mock(wraps=render.find_mask_contours)
    monkeypatch.setattr(render, "find_mask_contours", contours)
    cache = render.ShapeRenderCache(max_bytes=20_000, max_entries=1)
    first = _mask()
    second = _mask()
    assert second.mask is not None
    second.mask[0, 0] = True
    context = dataclasses.replace(_context(), fill_mask=False)
    for _ in range(3):
        cache.begin_paint()
        for shape in (first, second):
            _paint(shape=shape, context=context, cache=cache)
        assert len(cache._entries) == 1
        assert cache._size_bytes <= cache.max_bytes
    assert contours.call_count == 4
    # An unused resident can be replaced when the visible scene changes.
    cache.begin_paint()
    _paint(shape=second, context=context, cache=cache)
    assert contours.call_count == 5
    _paint(shape=second, context=context, cache=cache)
    assert contours.call_count == 5


def test_oversized_masks_bypass_cache() -> None:
    cache = render.ShapeRenderCache(max_bytes=10)
    shape = _mask()
    assert _paint(shape=shape, context=_context(), cache=cache) == _paint(
        shape=shape, context=_context(), cache=None
    )
    assert not cache._entries


def _polygon() -> Shape:
    return Shape(
        points=np.array([[25.0, 25.0], [90.0, 25.0], [90.0, 90.0], [25.0, 90.0]]),
        closed=True,
    )


def test_polygon_paths_reuse_content_across_copies_and_undo(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = Mock(wraps=render._build_shape_points_paths)
    monkeypatch.setattr(render, "_build_shape_points_paths", build)
    cache = render.ShapeRenderCache()
    shape = _polygon()
    context = dataclasses.replace(_context(), show_vertices=False)
    _paint(shape=shape, context=context, cache=cache)
    original = shape.copy()
    shape = shape.copy()
    _paint(
        shape=shape,
        context=dataclasses.replace(context, selected=True, fill=True),
        cache=cache,
    )
    assert build.call_count == 1
    shape.move_vertex(i=0, pos=[28.0, 30.0])
    _paint(shape=shape, context=context, cache=cache)
    assert build.call_count == 2
    _paint(shape=original.copy(), context=context, cache=cache)
    assert build.call_count == 2
    assert cache._size_bytes <= cache.max_bytes


@pytest.mark.parametrize("scale", [0.447, 1.0, 2.5])
@pytest.mark.parametrize("show_vertices", [False, True])
@pytest.mark.parametrize(
    "highlight",
    [
        None,
        render.VertexHighlight(index=0, mode="near"),
        render.VertexHighlight(index=1, mode="move"),
    ],
)
def test_cached_polygon_matches_pixels_through_render_state_changes(
    *,
    scale: float,
    show_vertices: bool,
    highlight: render.VertexHighlight | None,
) -> None:
    cache = render.ShapeRenderCache()
    shape = _polygon()
    _paint(shape=shape, context=_context(), cache=cache)
    context = dataclasses.replace(
        _context(), scale=scale, show_vertices=show_vertices, highlight=highlight
    )
    for changes in (
        {},
        {"selected": True, "fill": True},
        {"point_size": 12, "point_type": "square"},
    ):
        state = dataclasses.replace(context, **changes)
        for _ in range(2):
            cache.begin_paint()
            assert _paint(shape=shape, context=state, cache=cache) == _paint(
                shape=shape, context=state, cache=None
            )
    shape.closed = False
    assert _paint(shape=shape, context=context, cache=cache) == _paint(
        shape=shape, context=context, cache=None
    )


def test_oversized_polygon_bypasses_cache() -> None:
    cache = render.ShapeRenderCache(max_bytes=1)
    shape = _polygon()
    assert _paint(shape=shape, context=_context(), cache=cache) == _paint(
        shape=shape, context=_context(), cache=None
    )
    assert not cache._entries


@pytest.mark.parametrize("device_pixel_ratio", [1, 2])
def test_cached_overlapping_translucent_polygon_handles(
    *, device_pixel_ratio: int
) -> None:
    shape = Shape(
        points=np.array([[40.0, 40.0], [42.0, 40.0], [42.0, 42.0], [40.0, 42.0]]),
        closed=True,
    )
    palette = dataclasses.replace(
        _context().palette, line=QtGui.QColor(20, 80, 150, 128)
    )
    context = dataclasses.replace(
        _context(),
        palette=palette,
        fill=True,
        highlight=render.VertexHighlight(index=0, mode="near"),
    )
    cache = render.ShapeRenderCache()
    expected = _paint(
        shape=shape,
        context=context,
        cache=None,
        device_pixel_ratio=device_pixel_ratio,
        opacity=0.5,
    )
    for _ in range(2):
        cache.begin_paint()
        assert (
            _paint(
                shape=shape,
                context=context,
                cache=cache,
                device_pixel_ratio=device_pixel_ratio,
                opacity=0.5,
            )
            == expected
        )
