from __future__ import annotations

import importlib
import math

import numpy as np
import pytest

pytest.importorskip("pycocotools.mask")
labelme2coco = importlib.import_module("examples.instance_segmentation.labelme2coco")


def test_circle_to_polygon_segmentation_rejects_zero_radius() -> None:
    with pytest.raises(ValueError, match="Degenerate circle"):
        labelme2coco._circle_to_polygon_segmentation(center=(5.0, 5.0), edge=(5.0, 5.0))


@pytest.mark.parametrize("radius", [0.1, 1.0, 50.0, 100.0, 1_000.0])
def test_circle_to_polygon_segmentation_stays_within_one_pixel(
    *, radius: float
) -> None:
    coords = labelme2coco._circle_to_polygon_segmentation(
        center=(3.0, -2.0), edge=(3.0 + radius, -2.0)
    )
    points = np.array(coords).reshape(-1, 2)
    np.testing.assert_allclose(np.hypot(points[:, 0] - 3.0, points[:, 1] + 2.0), radius)
    n_vertices = len(points)
    assert n_vertices >= 12
    # Sagitta of a chord spanning 2*pi/n radians: the maximum distance the
    # polygon edge deviates from the true arc.
    assert radius * (1.0 - math.cos(math.pi / n_vertices)) <= 1.0
