from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from examples import utils


def _mask_shape(points: list[list[float]], mask: NDArray[np.bool_]) -> dict[str, Any]:
    return dict(
        label="car",
        points=points,
        shape_type="mask",
        flags={},
        description="",
        group_id=None,
        mask=mask,
        other_data={},
    )


def test_shapes_to_label_mask_paints_bbox_pixels() -> None:
    patch = np.ones((3, 5), dtype=bool)
    shape = _mask_shape(points=[[2.0, 1.0], [6.0, 3.0]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    painted = np.zeros((20, 20), dtype=bool)
    painted[1:4, 2:7] = True
    assert np.array_equal(cls > 0, painted)


def test_shapes_to_label_mask_clips_bbox_off_left_edge() -> None:
    patch = np.ones((3, 5), dtype=bool)
    shape = _mask_shape(points=[[-6.0, 1.0], [-2.0, 3.0]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    assert not (cls > 0).any()


def test_shapes_to_label_mask_clips_bbox_over_right_edge() -> None:
    patch = np.ones((3, 5), dtype=bool)
    shape = _mask_shape(points=[[17.0, 1.0], [21.0, 3.0]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    painted = np.zeros((20, 20), dtype=bool)
    painted[1:4, 17:20] = True
    assert np.array_equal(cls > 0, painted)


def test_shapes_to_label_mask_clips_bbox_off_top_left_corner() -> None:
    patch = np.zeros((5, 5), dtype=bool)
    patch[1, 2] = True  # -> canvas (0, 0)
    patch[4, 4] = True  # -> canvas (3, 2)
    shape = _mask_shape(points=[[-2.0, -1.0], [2.0, 3.0]], mask=patch)
    cls, _ = utils.shapes_to_label((20, 20), [shape], {"car": 1})
    painted = np.zeros((20, 20), dtype=bool)
    painted[0, 0] = True
    painted[3, 2] = True
    assert np.array_equal(cls > 0, painted)
