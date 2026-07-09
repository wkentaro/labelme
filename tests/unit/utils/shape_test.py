from __future__ import annotations

import numpy as np
import pytest

from labelme._label_file import ShapeDict
from labelme._utils import shape as shape_module

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


def test_shapes_to_label_places_mask_shape_at_its_bbox() -> None:
    # A "mask" shape carries a local boolean patch plus a bbox (2 points, xy).
    # The patch is composited into the full-image label maps at that bbox, with
    # the bbox upper bound inclusive. mask is indexed [row=y, col=x].
    patch = np.ones((3, 7), dtype=bool)
    patch[0, 0] = False  # cleared cell proves the patch content drives the fill
    shape = ShapeDict(
        label="car",
        points=[[2.0, 3.0], [8.0, 5.0]],  # x in [2, 8], y in [3, 5]
        shape_type="mask",
        flags={},
        description="",
        group_id=None,
        mask=patch,
        other_data={},
    )
    cls, ins = shape_module.shapes_to_label((20, 20), [shape], {"car": 1})
    assert cls[3, 2] == 0  # patch[0, 0] is False, so the bbox corner stays empty
    assert cls[3, 3] == 1
    assert cls[5, 8] == 1  # bottom-right corner; a row/col swap would miss it
    assert ins[5, 8] == 1
    assert cls[6, 8] == 0  # one row past the inclusive y2 bound
    assert cls[3, 9] == 0  # one col past the inclusive x2 bound


def test_shapes_to_label_raises_when_mask_shape_has_no_ndarray() -> None:
    shape = ShapeDict(
        label="car",
        points=[[0.0, 0.0], [3.0, 3.0]],
        shape_type="mask",
        flags={},
        description="",
        group_id=None,
        mask=None,
        other_data={},
    )
    with pytest.raises(ValueError, match=r"shape\['mask'\] must be numpy.ndarray"):
        shape_module.shapes_to_label((20, 20), [shape], {"car": 1})


def test_shapes_to_label_groups_instances_by_label_and_group_id() -> None:
    def _rectangle(points: list[list[float]], group_id: int) -> ShapeDict:
        return ShapeDict(
            label="car",
            points=points,
            shape_type="rectangle",
            flags={},
            description="",
            group_id=group_id,
            mask=None,
            other_data={},
        )

    shapes = [
        _rectangle([[0.0, 0.0], [4.0, 4.0]], group_id=1),
        _rectangle([[10.0, 10.0], [14.0, 14.0]], group_id=2),
        _rectangle([[16.0, 16.0], [19.0, 19.0]], group_id=1),
    ]
    cls, ins = shape_module.shapes_to_label((20, 20), shapes, {"car": 1})
    assert cls[2, 2] == 1
    assert cls[12, 12] == 1
    assert cls[17, 17] == 1
    assert ins[2, 2] == 1  # first (label, group_id) pair
    assert ins[12, 12] == 2  # different group_id -> distinct instance
    assert ins[17, 17] == 1  # same (label, group_id) as the first -> same instance


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


def test_shape_to_mask_circle_marks_center_and_clears_outside() -> None:
    # points are (x, y); the 2nd point sets the radius (here dist=5). Center
    # cx != cy so an x/y swap is caught. mask is indexed [row=y, col=x].
    mask = shape_module.shape_to_mask(
        img_shape=(30, 30),
        points=[[12.0, 10.0], [12.0, 15.0]],
        shape_type="circle",
    )
    assert mask.dtype == bool
    assert mask[10, 12]
    assert mask[12, 12]  # off the center row: a filled disk, not a horizontal line
    assert not mask[5, 7]  # bbox corner: clear for an ellipse, set for a rectangle
    assert not mask[10, 18]  # 1px past the radius-5 edge


def test_shape_to_mask_line_marks_pixels_along_segment() -> None:
    # points are (x, y); mask is indexed [row=y, col=x].
    mask = shape_module.shape_to_mask(
        img_shape=(100, 100),
        points=[[10.0, 50.0], [90.0, 50.0]],
        shape_type="line",
        line_width=10,
    )
    assert mask.dtype == bool
    assert mask[50, 10]
    assert mask[50, 50]
    assert mask[50, 90]
    assert mask[48, 50]  # off the centerline, within line_width=10
    assert not mask[10, 50]


def test_shape_to_mask_point_marks_pixels_around_center() -> None:
    # points are (x, y); cx != cy so an x/y swap is caught. mask is indexed
    # [row=y, col=x].
    mask = shape_module.shape_to_mask(
        img_shape=(100, 100),
        points=[[40.0, 60.0]],
        shape_type="point",
        point_size=5,
    )
    assert mask.dtype == bool
    assert mask[60, 40]
    assert mask[60, 43]  # 3px from center, inside point_size=5
    assert mask[62, 40]  # off the center row: a filled disk, not a horizontal line
    assert not mask[60, 46]  # 1px past the point_size=5 edge


def test_masks_to_bboxes_returns_yxyx_bboxes() -> None:
    masks = np.zeros((2, 10, 10), dtype=bool)
    masks[0, 2:5, 3:7] = True
    masks[1, 0:3, 0:4] = True
    bboxes = shape_module.masks_to_bboxes(masks)
    assert bboxes.shape == (2, 4)
    assert bboxes.dtype == np.float32
    # bboxes are returned in (y1, x1, y2, x2) order, not the more common xyxy.
    assert np.array_equal(bboxes[0], [2, 3, 5, 7])
    assert np.array_equal(bboxes[1], [0, 0, 3, 4])


def test_masks_to_bboxes_raises_for_wrong_ndim() -> None:
    masks = np.zeros((10, 10), dtype=bool)
    with pytest.raises(ValueError, match=r"masks\.ndim must be 3"):
        shape_module.masks_to_bboxes(masks)


def test_masks_to_bboxes_raises_for_non_bool_dtype() -> None:
    masks = np.zeros((1, 10, 10), dtype=np.uint8)
    with pytest.raises(ValueError, match=r"masks\.dtype must be bool"):
        shape_module.masks_to_bboxes(masks)


def test_masks_to_bboxes_raises_for_all_false_mask() -> None:
    # An all-False mask has no foreground pixels, so no bbox is defined: the
    # implementation currently raises rather than returning a sentinel. Pin that
    # behavior without depending on numpy's internal message.
    masks = np.zeros((1, 10, 10), dtype=bool)
    with pytest.raises(ValueError):
        shape_module.masks_to_bboxes(masks)
