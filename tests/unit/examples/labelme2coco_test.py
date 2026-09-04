from __future__ import annotations

import math
from typing import Final

import numpy as np
import pytest

# Importing the module must not require pycocotools: that dependency is only
# pulled in inside main(), specifically so geometry helpers like this one
# stay testable without it installed.
from examples.instance_segmentation import labelme2coco

_CIRCLE_MIN_VERTEX_COUNT: Final = 12


def test_circle_to_polygon_segmentation_rejects_zero_radius() -> None:
    with pytest.raises(ValueError, match="Degenerate circle"):
        labelme2coco._circle_to_polygon_segmentation(center=(5.0, 5.0), edge=(5.0, 5.0))


def test_circle_to_polygon_segmentation_returns_flattened_xy_pairs() -> None:
    coords = labelme2coco._circle_to_polygon_segmentation(
        center=(0.0, 0.0), edge=(10.0, 0.0)
    )
    assert len(coords) % 2 == 0
    points = np.array(coords).reshape(-1, 2)
    distances = np.hypot(points[:, 0], points[:, 1])
    np.testing.assert_allclose(distances, 10.0)


@pytest.mark.parametrize("radius", [0.1, 1.0])
def test_circle_to_polygon_segmentation_never_drops_below_min_vertices(
    *, radius: float
) -> None:
    coords = labelme2coco._circle_to_polygon_segmentation(
        center=(0.0, 0.0), edge=(radius, 0.0)
    )
    n_vertices = len(coords) // 2
    assert n_vertices >= _CIRCLE_MIN_VERTEX_COUNT


def test_circle_to_polygon_segmentation_radius_100_stays_within_one_pixel() -> None:
    radius = 100.0
    coords = labelme2coco._circle_to_polygon_segmentation(
        center=(0.0, 0.0), edge=(radius, 0.0)
    )
    n_vertices = len(coords) // 2
    # Sagitta of a chord spanning 2*pi/n radians of a circle with this
    # radius: the maximum distance the chord deviates from the true arc.
    max_deviation = radius * (1.0 - math.cos(math.pi / n_vertices))
    assert max_deviation <= 1.0


def test_circle_to_polygon_segmentation_refines_large_circles() -> None:
    radius = 1_000.0
    coords = labelme2coco._circle_to_polygon_segmentation(
        center=(0.0, 0.0), edge=(radius, 0.0)
    )
    n_vertices = len(coords) // 2
    assert n_vertices > _CIRCLE_MIN_VERTEX_COUNT
    refinements = n_vertices // _CIRCLE_MIN_VERTEX_COUNT
    assert refinements & (refinements - 1) == 0
