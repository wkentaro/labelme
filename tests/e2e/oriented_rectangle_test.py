from __future__ import annotations

import math
from typing import Final

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.widgets.canvas import Canvas

from ..conftest import close_or_pause
from .conftest import click_canvas_fraction
from .conftest import drag_canvas
from .conftest import hover_widget_pos
from .conftest import image_to_widget_pos
from .conftest import submit_label_dialog


def _centroid(points: np.ndarray) -> QPointF:
    return QPointF(float(points[:, 0].mean()), float(points[:, 1].mean()))


def _edge_lengths(points: np.ndarray) -> list[float]:
    n = len(points)
    return [float(np.linalg.norm(points[(i + 1) % n] - points[i])) for i in range(n)]


def _vertex_displacements(actual: np.ndarray, original: list[QPointF]) -> list[float]:
    return [
        math.hypot(float(actual[i][0]) - o.x(), float(actual[i][1]) - o.y())
        for i, o in enumerate(original)
    ]


def _draw_oriented_rectangle(
    qtbot: QtBot,
    win: MainWindow,
    label: str,
    clicks: tuple[tuple[float, float], ...],
) -> None:
    canvas: Canvas = win._canvas_widgets.canvas
    win._switch_canvas_mode(edit=False, create_mode="oriented_rectangle")
    qtbot.wait(50)
    submit_label_dialog(qtbot=qtbot, label_dialog=win._label_dialog, label=label)
    for xy in clicks:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)
    qtbot.waitUntil(lambda: any(s.label == label for s in canvas.shapes))


@pytest.mark.gui
def test_drag_rotation_handle_rotates_oriented_rectangle(
    qtbot: QtBot,
    raw_win: MainWindow,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    _draw_oriented_rectangle(
        qtbot=qtbot,
        win=raw_win,
        label="rect",
        clicks=((0.25, 0.5), (0.5, 0.5), (0.5, 0.75)),
    )
    shape = next(s for s in canvas.shapes if s.label == "rect")
    original_points = [QPointF(float(p[0]), float(p[1])) for p in shape.points]
    original_centroid = _centroid(shape.points)
    original_edges = _edge_lengths(shape.points)

    raw_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    p0, p1 = original_points[0], original_points[1]
    handle = QPointF((p0.x() + p1.x()) / 2, (p0.y() + p1.y()) / 2)
    relative = handle - original_centroid
    angle = math.pi / 2
    target = original_centroid + QPointF(
        relative.x() * math.cos(angle) - relative.y() * math.sin(angle),
        relative.x() * math.sin(angle) + relative.y() * math.cos(angle),
    )

    handle_widget = image_to_widget_pos(canvas=canvas, image_pos=handle)
    target_widget = image_to_widget_pos(canvas=canvas, image_pos=target)
    qtbot.mouseMove(canvas, pos=handle_widget)
    qtbot.wait(100)
    assert canvas._hovered_rotation == 1

    drag_canvas(
        qtbot=qtbot,
        canvas=canvas,
        button=Qt.LeftButton,
        start=handle_widget,
        end=target_widget,
    )

    rotated_centroid = _centroid(shape.points)
    assert rotated_centroid.x() == pytest.approx(original_centroid.x(), abs=1.0)
    assert rotated_centroid.y() == pytest.approx(original_centroid.y(), abs=1.0)

    rotated_edges = _edge_lengths(shape.points)
    for actual, expected in zip(rotated_edges, original_edges):
        assert actual == pytest.approx(expected, abs=1.0)

    moved = _vertex_displacements(actual=shape.points, original=original_points)
    assert min(moved) > 1.0

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_drag_vertex_out_of_pixmap_clips_oriented_rectangle(
    qtbot: QtBot,
    raw_win: MainWindow,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    pixmap = canvas.pixmap
    assert pixmap is not None
    pixmap_width = float(pixmap.width())
    pixmap_height = float(pixmap.height())

    # Axis-aligned rect with the moving corner (vertex 2) starting in the
    # interior. Vertex order produced by oriented-rectangle creation:
    #   0 = anchor, 1 = end of locked edge, 2 = moving (opposite anchor),
    #   3 = perpendicular adjacent.
    _draw_oriented_rectangle(
        qtbot=qtbot,
        win=raw_win,
        label="rect",
        clicks=((0.3, 0.4), (0.7, 0.4), (0.7, 0.6)),
    )
    shape = next(s for s in canvas.shapes if s.label == "rect")

    raw_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    original_points = [QPointF(float(p[0]), float(p[1])) for p in shape.points]
    moving_vertex = QPointF(float(shape.points[2][0]), float(shape.points[2][1]))
    # Drag past the top edge of the image so the unclipped target lies above
    # the pixmap. The clip logic must keep all four corners inside the image
    # while preserving the parallelogram.
    target_image_pos = QPointF(moving_vertex.x(), -pixmap_height)

    start_widget = image_to_widget_pos(canvas=canvas, image_pos=moving_vertex)
    end_widget = image_to_widget_pos(canvas=canvas, image_pos=target_image_pos)
    hover_widget_pos(qtbot=qtbot, canvas=canvas, pos=start_widget)
    assert canvas._hovered_vertex == 2
    drag_canvas(
        qtbot=qtbot,
        canvas=canvas,
        button=Qt.LeftButton,
        start=start_widget,
        end=end_widget,
    )

    moved = _vertex_displacements(actual=shape.points, original=original_points)
    assert max(moved) > 1.0, "Drag did not move any vertex"

    _CLIP_TOLERANCE: Final = 1e-3
    for point in shape.points:
        assert -_CLIP_TOLERANCE <= float(point[0]) <= pixmap_width + _CLIP_TOLERANCE
        assert -_CLIP_TOLERANCE <= float(point[1]) <= pixmap_height + _CLIP_TOLERANCE

    p0, p1, p2, p3 = shape.points
    side_01 = p1 - p0
    side_32 = p2 - p3
    assert float(side_01[0]) == pytest.approx(float(side_32[0]), abs=1e-3)
    assert float(side_01[1]) == pytest.approx(float(side_32[1]), abs=1e-3)

    edges = _edge_lengths(shape.points)
    assert min(edges) > 1.0

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_oriented_rectangle_disallows_add_and_remove_point(
    qtbot: QtBot,
    raw_win: MainWindow,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    _draw_oriented_rectangle(
        qtbot=qtbot,
        win=raw_win,
        label="rect",
        clicks=((0.3, 0.4), (0.7, 0.4), (0.7, 0.6)),
    )
    shape = next(s for s in canvas.shapes if s.label == "rect")
    num_points = len(shape.points)

    raw_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    # Hovering over an edge midpoint enables `add_point_to_edge` for polygons,
    # but oriented_rectangle's `can_add_point()` is False so the canvas must
    # leave the action disabled.
    assert shape.can_add_point() is False
    p0, p1 = shape.points[0], shape.points[1]
    edge_midpoint = QPointF(
        (float(p0[0]) + float(p1[0])) / 2, (float(p0[1]) + float(p1[1])) / 2
    )
    edge_widget = image_to_widget_pos(canvas=canvas, image_pos=edge_midpoint)
    hover_widget_pos(qtbot=qtbot, canvas=canvas, pos=edge_widget)
    assert not raw_win._actions.add_point_to_edge.isEnabled()

    # Alt+Shift+Click on a vertex removes points from polygons; for
    # oriented_rectangle `Shape.remove_point` bails out because
    # `can_remove_point()` is False, so the vertex count must not change.
    vertex_widget = image_to_widget_pos(
        canvas=canvas,
        image_pos=QPointF(float(shape.points[0][0]), float(shape.points[0][1])),
    )
    hover_widget_pos(qtbot=qtbot, canvas=canvas, pos=vertex_widget)
    qtbot.mouseClick(
        canvas,
        Qt.LeftButton,
        Qt.AltModifier | Qt.ShiftModifier,
        pos=vertex_widget,
    )
    qtbot.wait(50)
    assert len(shape.points) == num_points

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)
