from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from labelme._automation import Detection
from labelme._automation import shapes_from_detections


def test_shapes_from_detections_rectangle_uses_bbox() -> None:
    [shape] = shapes_from_detections(
        detections=[Detection(bbox=(10, 20, 30, 50))],
        shape_type="rectangle",
    )

    assert shape.shape_type == "rectangle"
    assert (shape.points[0][0], shape.points[0][1]) == pytest.approx((10, 20))
    assert (shape.points[1][0], shape.points[1][1]) == pytest.approx((30, 50))


def test_shapes_from_detections_rectangle_without_bbox_is_dropped() -> None:
    shapes = shapes_from_detections(
        detections=[Detection(mask=np.ones((5, 5), dtype=bool))],
        shape_type="rectangle",
    )

    assert shapes == []


def test_shapes_from_detections_circle_with_mask_uses_centroid_and_area() -> None:
    [shape] = shapes_from_detections(
        detections=[
            Detection(
                bbox=(10, 20, 30, 50),
                mask=np.ones((31, 21), dtype=bool),
            )
        ],
        shape_type="circle",
    )

    assert shape.shape_type == "circle"
    expected_cx = 10 + 10
    expected_cy = 20 + 15
    expected_radius = math.sqrt(21 * 31 / math.pi)
    assert shape.points[0][0] == pytest.approx(expected_cx)
    assert shape.points[0][1] == pytest.approx(expected_cy)
    assert shape.points[1][0] == pytest.approx(expected_cx + expected_radius)
    assert shape.points[1][1] == pytest.approx(expected_cy)


def test_shapes_from_detections_circle_without_mask_falls_back_to_inscribed() -> None:
    [shape] = shapes_from_detections(
        detections=[Detection(bbox=(0, 0, 10, 20))],
        shape_type="circle",
    )

    assert shape.shape_type == "circle"
    assert shape.points[0][0] == pytest.approx(5)
    assert shape.points[0][1] == pytest.approx(10)
    assert shape.points[1][0] == pytest.approx(10)
    assert shape.points[1][1] == pytest.approx(10)


def test_shapes_from_detections_oriented_rectangle_with_mask_uses_min_area_rect() -> (
    None
):
    # Wider-than-tall rectangular mask: long axis is +x in mask-local coords,
    # so corners trace (xmin, ymin) → (xmax, ymin) → (xmax, ymax) → (xmin, ymax).
    # World corners are mask-local corners offset by the bbox origin.
    [shape] = shapes_from_detections(
        detections=[
            Detection(
                bbox=(10, 20, 30, 30),
                mask=np.ones((11, 21), dtype=bool),
            )
        ],
        shape_type="oriented_rectangle",
    )

    assert shape.shape_type == "oriented_rectangle"
    expected = [(10, 20), (30, 20), (30, 30), (10, 30)]
    for i, (x, y) in enumerate(expected):
        assert (shape.points[i][0], shape.points[i][1]) == pytest.approx((x, y))


def test_shapes_from_detections_oriented_rectangle_without_mask_falls_back() -> None:
    [shape] = shapes_from_detections(
        detections=[Detection(bbox=(0, 0, 10, 20))],
        shape_type="oriented_rectangle",
    )

    assert shape.shape_type == "oriented_rectangle"
    expected = [(0, 0), (10, 0), (10, 20), (0, 20)]
    for i, (x, y) in enumerate(expected):
        assert (shape.points[i][0], shape.points[i][1]) == pytest.approx((x, y))


def test_shapes_from_detections_oriented_rectangle_with_rotated_mask(
    rotated_rectangle_mask: NDArray[np.bool_],
    rotated_rectangle_angle: float,
) -> None:
    # The mask is centered at (20, 20); placing it at bbox origin (50, 100)
    # offsets the world center to (70, 120).
    [shape] = shapes_from_detections(
        detections=[Detection(bbox=(50, 100, 90, 140), mask=rotated_rectangle_mask)],
        shape_type="oriented_rectangle",
    )

    assert shape.shape_type == "oriented_rectangle"
    edge_dx = shape.points[1][0] - shape.points[0][0]
    edge_dy = shape.points[1][1] - shape.points[0][1]
    recovered_angle = math.atan2(edge_dy, edge_dx)
    assert recovered_angle == pytest.approx(
        rotated_rectangle_angle, abs=math.radians(3)
    )
    center_x = sum(shape.points[i][0] for i in range(4)) / 4
    center_y = sum(shape.points[i][1] for i in range(4)) / 4
    assert center_x == pytest.approx(70.0, abs=0.5)
    assert center_y == pytest.approx(120.0, abs=0.5)


def test_shapes_from_detections_oriented_rectangle_with_square_mask() -> None:
    # The minimum-area rectangle of a square mask is the axis-aligned bbox,
    # so the offset corners trace the bbox itself.
    [shape] = shapes_from_detections(
        detections=[Detection(bbox=(0, 0, 10, 10), mask=np.ones((11, 11), dtype=bool))],
        shape_type="oriented_rectangle",
    )

    assert shape.shape_type == "oriented_rectangle"
    expected = [(0, 0), (10, 0), (10, 10), (0, 10)]
    for i, (x, y) in enumerate(expected):
        assert (shape.points[i][0], shape.points[i][1]) == pytest.approx((x, y))


def test_shapes_from_detections_oriented_rectangle_square_mask_no_bbox() -> None:
    # Without a bbox the mask coordinates are emitted as-is; the square mask
    # still produces a valid axis-aligned rectangle rather than being dropped.
    [shape] = shapes_from_detections(
        detections=[Detection(mask=np.ones((11, 11), dtype=bool))],
        shape_type="oriented_rectangle",
    )

    assert shape.shape_type == "oriented_rectangle"
    expected = [(0, 0), (10, 0), (10, 10), (0, 10)]
    for i, (x, y) in enumerate(expected):
        assert (shape.points[i][0], shape.points[i][1]) == pytest.approx((x, y))


def test_shapes_from_detections_mask_drops_empty_mask() -> None:
    # OSAM occasionally returns a bbox whose segmentation mask is all-False;
    # without this guard the shape would render as bbox-only (no visible mask).
    shapes = shapes_from_detections(
        detections=[
            Detection(bbox=(10, 20, 30, 50), mask=np.zeros((31, 21), dtype=bool))
        ],
        shape_type="mask",
    )
    assert shapes == []
