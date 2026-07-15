from __future__ import annotations

from labelme._app import _shapes_from_dicts
from labelme._utils.shape import ShapeDict


def _shape_dict(label: str) -> ShapeDict:
    return ShapeDict(
        label=label,
        points=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        shape_type="polygon",
        flags={},
        description="",
        group_id=None,
        mask=None,
        other_data={},
    )


def test_invalid_label_flags_pattern_is_skipped() -> None:
    shapes = _shapes_from_dicts(
        shape_dicts=[_shape_dict(label="cat")],
        label_flags={"cat(": ["occluded"]},
    )
    assert shapes[0].flags == {}


def test_valid_label_flags_pattern_applies_despite_an_invalid_one() -> None:
    shapes = _shapes_from_dicts(
        shape_dicts=[_shape_dict(label="cat")],
        label_flags={"cat(": ["broken"], "cat": ["occluded"]},
    )
    assert shapes[0].flags == {"occluded": False}
