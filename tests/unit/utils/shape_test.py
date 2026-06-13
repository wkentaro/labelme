from __future__ import annotations

import numpy as np
import pytest

from labelme._label_file import ShapeDict
from labelme.utils import shape as shape_module

from .util import get_img_and_data


def test_shapes_to_label() -> None:
    img, data = get_img_and_data()
    label_name_to_value = {}
    for shape in data["shapes"]:
        label_name = shape["label"]
        label_value = len(label_name_to_value)
        label_name_to_value[label_name] = label_value
    cls, _ = shape_module.shapes_to_label(
        img.shape, data["shapes"], label_name_to_value
    )
    assert cls.shape == img.shape[:2]


def test_shapes_to_label_raises_clear_error_for_unknown_label() -> None:
    shape = ShapeDict(
        label="car",
        points=[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]],
        shape_type="polygon",
        flags={},
        description="",
        group_id=None,
        mask=None,
        other_data={},
    )
    with pytest.raises(ValueError, match="shape labels not in the provided labels"):
        shape_module.shapes_to_label((20, 20), [shape], {"road": 1})


def test_shape_to_mask() -> None:
    img, data = get_img_and_data()
    for shape in data["shapes"]:
        points = shape["points"]
        mask = shape_module.shape_to_mask(img.shape[:2], points)
        assert mask.shape == img.shape[:2]


def test_shape_to_mask_oriented_rectangle_marks_inside_pixels() -> None:
    # Rect spans x in [0, 10], y in [0, 4]; mask is indexed (row=y, col=x).
    mask = shape_module.shape_to_mask(
        img_shape=(20, 20),
        points=[[0.0, 0.0], [10.0, 0.0], [10.0, 4.0], [0.0, 4.0]],
        shape_type="oriented_rectangle",
    )
    assert mask.dtype == bool
    inside_row, inside_col = 2, 5
    outside_row, outside_col = 15, 15
    assert mask[inside_row, inside_col]
    assert not mask[outside_row, outside_col]


def test_shape_to_mask_linestrip_fills_notch_at_turning_point() -> None:
    # Acute V with the apex at (50, 50) and both arms going up; the convex side
    # is below the apex. A plain wide line leaves an unfilled notch there (#2124).
    img_shape = (100, 100)
    line_width = 25
    apex_x, apex_y = 50, 50
    mask = shape_module.shape_to_mask(
        img_shape=img_shape,
        points=[[40.0, 10.0], [apex_x, apex_y], [60.0, 10.0]],
        shape_type="linestrip",
        line_width=line_width,
    )
    join_below_apex = mask[apex_y : apex_y + line_width // 2, apex_x]
    assert join_below_apex.all(), f"notch left unfilled below apex: {join_below_apex}"


def test_shape_to_mask_linestrip_collinear_point_does_not_change_mask() -> None:
    img_shape = (100, 100)
    line_width = 25
    with_midpoint = shape_module.shape_to_mask(
        img_shape,
        [[10.0, 50.0], [50.0, 50.0], [90.0, 50.0]],
        shape_type="linestrip",
        line_width=line_width,
    )
    without_midpoint = shape_module.shape_to_mask(
        img_shape,
        [[10.0, 50.0], [90.0, 50.0]],
        shape_type="linestrip",
        line_width=line_width,
    )
    assert np.array_equal(with_midpoint, without_midpoint)


def test_shape_to_mask_rectangle_reversed_coords() -> None:
    img_shape = (100, 100)
    mask_tl_br = shape_module.shape_to_mask(
        img_shape, [[10, 10], [50, 50]], shape_type="rectangle"
    )
    mask_br_tl = shape_module.shape_to_mask(
        img_shape, [[50, 50], [10, 10]], shape_type="rectangle"
    )
    mask_tr_bl = shape_module.shape_to_mask(
        img_shape, [[50, 10], [10, 50]], shape_type="rectangle"
    )
    mask_bl_tr = shape_module.shape_to_mask(
        img_shape, [[10, 50], [50, 10]], shape_type="rectangle"
    )
    assert np.array_equal(mask_tl_br, mask_br_tl)
    assert np.array_equal(mask_tl_br, mask_tr_bl)
    assert np.array_equal(mask_tl_br, mask_bl_tr)
    assert mask_tl_br.sum() > 0
