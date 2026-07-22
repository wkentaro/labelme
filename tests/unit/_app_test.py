from __future__ import annotations

import numpy as np
import pytest

from labelme import __appname__
from labelme import _app
from labelme import _automation
from labelme._shape import Shape


@pytest.mark.parametrize(
    "create_mode, ai_output_format, expected",
    [
        ("ai_points_to_shape", "mask", "mask"),
        ("ai_box_to_shape", "polygon", "polygon"),
        ("polygon", "mask", "polygon"),
        ("rectangle", "mask", "rectangle"),
        ("edit", "polygon", None),
    ],
    ids=[
        "ai-points-passthrough",
        "ai-box-passthrough",
        "text-polygon",
        "text-rectangle",
        "unrelated-mode",
    ],
)
def test_resolve_text_annotation_shape_type(
    create_mode: str,
    ai_output_format: _automation.AiOutputFormat,
    expected: _automation.AiOutputFormat | None,
) -> None:
    assert (
        _app._resolve_text_annotation_shape_type(
            create_mode=create_mode, ai_output_format=ai_output_format
        )
        == expected
    )


@pytest.mark.parametrize(
    "label, label_colors, expected",
    [
        ("cat", None, None),
        ("cat", {}, None),
        ("cat", {"dog": [1, 2, 3]}, None),
        ("cat", {"cat": [255, 0, 128]}, (255, 0, 128)),
        ("cat", {"cat": [0, 0, 0]}, (0, 0, 0)),
    ],
    ids=[
        "colors-none",
        "colors-empty",
        "label-not-in-colors",
        "valid-rgb",
        "valid-rgb-zero-bound",
    ],
)
def test_rgb_from_label_colors_returns_rgb_or_none(
    label: str,
    label_colors: dict[str, list[int]] | None,
    expected: tuple[int, int, int] | None,
) -> None:
    assert (
        _app._rgb_from_label_colors(label=label, label_colors=label_colors) == expected
    )


@pytest.mark.parametrize(
    "rgb",
    [[256, 0, 0], [-1, 0, 0], [0, 0], [0, 0, 0, 0]],
    ids=[
        "channel-too-high",
        "channel-too-low",
        "too-few-channels",
        "too-many-channels",
    ],
)
def test_rgb_from_label_colors_rejects_invalid_rgb(rgb: list[int]) -> None:
    with pytest.raises(ValueError, match="0-255 RGB tuple"):
        _app._rgb_from_label_colors(label="cat", label_colors={"cat": rgb})


@pytest.mark.parametrize(
    "label, existing_labels, policy, expected",
    [
        ("cat", [], None, True),
        ("cat", ["cat"], "exact", True),
        ("cat", ["dog"], "exact", False),
        ("cat", ["cat"], "unknown", False),
    ],
    ids=["policy-none", "exact-match", "exact-no-match", "unknown-policy"],
)
def test_is_valid_label(
    label: str, existing_labels: list[str], policy: str | None, expected: bool
) -> None:
    assert (
        _app._is_valid_label(
            label=label, existing_labels=existing_labels, policy=policy
        )
        is expected
    )


@pytest.mark.parametrize(
    "image_path, file_index, file_count, dirty, expected",
    [
        (None, None, 0, False, __appname__),
        ("img.png", None, 0, False, f"{__appname__} - img.png"),
        ("img.png", 1, 5, False, f"{__appname__} - img.png [2/5]"),
        ("img.png", 0, 5, False, f"{__appname__} - img.png [1/5]"),
        ("img.png", 0, 0, False, f"{__appname__} - img.png"),
        ("img.png", None, 5, False, f"{__appname__} - img.png"),
        ("img.png", 1, 5, True, f"{__appname__} - img.png [2/5]*"),
        (None, None, 0, True, f"{__appname__}*"),
        ("img.png", None, 0, True, f"{__appname__} - img.png*"),
    ],
    ids=[
        "appname-only",
        "path-no-index",
        "path-with-index",
        "first-file-index-zero",
        "index-set-count-zero",
        "count-set-no-index",
        "path-index-dirty",
        "appname-dirty",
        "path-dirty",
    ],
)
def test_format_window_title(
    image_path: str | None,
    file_index: int | None,
    file_count: int,
    dirty: bool,
    expected: str,
) -> None:
    assert (
        _app._format_window_title(
            image_path=image_path,
            file_index=file_index,
            file_count=file_count,
            dirty=dirty,
        )
        == expected
    )


def test_shape_to_dict_maps_all_fields() -> None:
    shape = Shape(
        label="cat",
        group_id=3,
        shape_type="rectangle",
        flags={"occluded": True},
        description="a cat",
        points=np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float64),
        other_data={"source": "human"},
    )

    result = _app._shape_to_dict(shape)

    assert result == {
        "label": "cat",
        "points": [[0.0, 1.0], [2.0, 3.0]],
        "shape_type": "rectangle",
        "flags": {"occluded": True},
        "description": "a cat",
        "group_id": 3,
        "mask": None,
        "other_data": {"source": "human"},
    }
    assert result["other_data"] is shape.other_data


@pytest.mark.parametrize(
    "flags, description, expected_flags, expected_description",
    [
        (None, None, {}, ""),
        ({"occluded": True}, "note", {"occluded": True}, "note"),
    ],
    ids=[
        "none-coalesced",
        "values-preserved",
    ],
)
def test_shape_to_dict_coalesces_optional_flags_and_description(
    flags: dict[str, bool] | None,
    description: str | None,
    expected_flags: dict[str, bool],
    expected_description: str,
) -> None:
    shape = Shape(label="cat", flags=flags, description=description)

    result = _app._shape_to_dict(shape)

    assert result["flags"] == expected_flags
    assert result["description"] == expected_description


def test_shape_to_dict_passes_mask_through_unchanged() -> None:
    mask = np.zeros((2, 2), dtype=bool)
    shape = Shape(
        label="cat",
        shape_type="mask",
        mask=mask,
        points=np.array([[0.0, 0.0], [1.0, 1.0]], dtype=np.float64),
    )

    assert _app._shape_to_dict(shape)["mask"] is mask


def test_shape_to_dict_requires_label() -> None:
    shape = Shape(label=None)

    with pytest.raises(AssertionError):
        _app._shape_to_dict(shape)
