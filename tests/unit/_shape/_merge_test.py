from __future__ import annotations

import numpy as np
import pytest

from labelme._shape import Shape
from labelme._shape import can_merge_shapes
from labelme._shape import merge_masks


def _full_mask(*, xmin: float, ymin: float, size: int, label: str) -> Shape:
    return Shape(
        label=label,
        shape_type="mask",
        mask=np.ones((size, size), dtype=bool),
        points=np.array([[xmin, ymin], [xmin + size - 1, ymin + size - 1]]),
    )


def test_merge_overlapping_masks_ors_pixels() -> None:
    a = _full_mask(xmin=0, ymin=0, size=3, label="cat")
    b = _full_mask(xmin=2, ymin=2, size=3, label="cat")

    merged = merge_masks([a, b])

    expected = np.zeros((5, 5), dtype=bool)
    expected[0:3, 0:3] = True
    expected[2:5, 2:5] = True
    assert merged.shape_type == "mask"
    assert merged.points.tolist() == [[0, 0], [4, 4]]
    np.testing.assert_array_equal(merged.mask, expected)


def test_merge_disjoint_masks_keeps_both_lands() -> None:
    a = _full_mask(xmin=0, ymin=0, size=2, label="cat")
    b = _full_mask(xmin=5, ymin=5, size=2, label="cat")

    merged = merge_masks([a, b])

    expected = np.zeros((7, 7), dtype=bool)
    expected[0:2, 0:2] = True
    expected[5:7, 5:7] = True
    assert merged.points.tolist() == [[0, 0], [6, 6]]
    np.testing.assert_array_equal(merged.mask, expected)


def test_merge_nested_masks_keeps_outer_bbox() -> None:
    inner = _full_mask(xmin=12, ymin=12, size=2, label="cat")
    outer = _full_mask(xmin=10, ymin=10, size=6, label="cat")

    merged = merge_masks([inner, outer])

    assert merged.points.tolist() == [[10, 10], [15, 15]]
    np.testing.assert_array_equal(merged.mask, np.ones((6, 6), dtype=bool))


def test_merge_rounds_non_integer_bbox_like_ai_assist() -> None:
    # Ties go to even, as int(round(x)) does: 0.5 -> 0, 2.5 -> 2, 1.5 -> 2.
    a = _full_mask(xmin=0.5, ymin=1.5, size=2, label="cat")
    b = _full_mask(xmin=2.5, ymin=0.5, size=2, label="cat")

    merged = merge_masks([a, b])

    assert merged.points.tolist() == [[0, 0], [4, 3]]
    expected = np.zeros((4, 5), dtype=bool)
    expected[2:4, 0:2] = True
    expected[0:2, 2:4] = True
    np.testing.assert_array_equal(merged.mask, expected)


def test_merge_takes_identity_from_first_shape() -> None:
    a = _full_mask(xmin=0, ymin=0, size=2, label="cat")
    a.group_id = 7
    a.flags = {"occluded": True}
    a.description = "first"
    a.other_data = {"extra": 1}
    b = _full_mask(xmin=1, ymin=1, size=2, label="cat")
    b.group_id = 9
    b.flags = {"occluded": False}
    b.description = "second"
    b.other_data = {"extra": 2}

    merged = merge_masks([a, b])

    assert merged.label == "cat"
    assert merged.group_id == 7
    assert merged.flags == {"occluded": True}
    assert merged.description == "first"
    assert merged.other_data == {"extra": 1}
    assert merged.flags is not a.flags
    assert merged is not a


@pytest.mark.parametrize(
    "shapes",
    [
        [],
        [_full_mask(xmin=0, ymin=0, size=2, label="cat")],
        [
            _full_mask(xmin=0, ymin=0, size=2, label="cat"),
            _full_mask(xmin=0, ymin=0, size=2, label="dog"),
        ],
        [
            _full_mask(xmin=0, ymin=0, size=2, label="cat"),
            Shape(
                label="cat",
                shape_type="rectangle",
                points=np.array([[0.0, 0.0], [2.0, 2.0]]),
            ),
        ],
    ],
    ids=["empty", "single", "mixed-labels", "non-mask"],
)
def test_can_merge_shapes_rejects(*, shapes: list[Shape]) -> None:
    assert not can_merge_shapes(shapes)
    with pytest.raises(ValueError, match="Mask Shapes"):
        merge_masks(shapes)


def test_can_merge_shapes_accepts_two_masks_with_one_label() -> None:
    shapes = [
        _full_mask(xmin=0, ymin=0, size=2, label="cat"),
        _full_mask(xmin=3, ymin=3, size=2, label="cat"),
    ]
    assert can_merge_shapes(shapes)
