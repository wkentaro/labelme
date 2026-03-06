import numpy as np
import pytest

from labelme.utils import shape as shape_module

from .util import get_img_and_data


def test_shapes_to_label():
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


def test_shape_to_mask():
    img, data = get_img_and_data()
    for shape in data["shapes"]:
        points = shape["points"]
        mask = shape_module.shape_to_mask(img.shape[:2], points)
        assert mask.shape == img.shape[:2]


def test_shape_to_mask_rectangle_reversed_coords():
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


def test_shape_to_mask_circle():
    img_shape = (100, 100)
    # Center at (50, 50), radius point at (60, 50) → radius = 10
    mask = shape_module.shape_to_mask(
        img_shape, [[50, 50], [60, 50]], shape_type="circle"
    )
    assert mask.shape == img_shape
    assert mask.dtype == bool
    assert mask.sum() > 0, "Circle mask should be non-empty"
    # Pixels far from center should not be filled
    assert not mask[0, 0], "Corner pixel should not be in circle mask"


def test_shape_to_mask_point():
    img_shape = (100, 100)
    mask = shape_module.shape_to_mask(img_shape, [[50, 50]], shape_type="point")
    assert mask.shape == img_shape
    assert mask.dtype == bool
    assert mask.sum() > 0, "Point mask should be non-empty"


def test_shape_to_mask_line():
    img_shape = (100, 100)
    mask = shape_module.shape_to_mask(
        img_shape, [[10, 10], [90, 90]], shape_type="line"
    )
    assert mask.shape == img_shape
    assert mask.dtype == bool
    assert mask.sum() > 0, "Line mask should be non-empty"


def test_shape_to_mask_invalid_shape_type():
    img_shape = (100, 100)
    with pytest.raises(ValueError, match="is not supported"):
        shape_module.shape_to_mask(
            img_shape, [[10, 10], [50, 50], [10, 50]], shape_type="triangle"
        )


def test_masks_to_bboxes():
    mask1 = np.zeros((50, 50), dtype=bool)
    mask1[10:20, 5:15] = True
    mask2 = np.zeros((50, 50), dtype=bool)
    mask2[30:40, 25:35] = True
    masks = np.stack([mask1, mask2])
    bboxes = shape_module.masks_to_bboxes(masks)
    assert bboxes.shape == (2, 4)
    assert bboxes.dtype == np.float32
    # mask1: rows 10-20, cols 5-15 → (y1, x1, y2, x2) = (10, 5, 20, 15)
    np.testing.assert_array_equal(bboxes[0], [10, 5, 20, 15])
    # mask2: rows 30-40, cols 25-35 → (y1, x1, y2, x2) = (30, 25, 40, 35)
    np.testing.assert_array_equal(bboxes[1], [30, 25, 40, 35])


def test_masks_to_bboxes_wrong_ndim():
    mask = np.zeros((50, 50), dtype=bool)
    with pytest.raises(ValueError, match="ndim must be 3"):
        shape_module.masks_to_bboxes(mask)


def test_masks_to_bboxes_wrong_dtype():
    masks = np.zeros((1, 50, 50), dtype=np.uint8)
    with pytest.raises(ValueError, match="dtype must be bool"):
        shape_module.masks_to_bboxes(masks)
