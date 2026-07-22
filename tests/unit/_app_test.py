from __future__ import annotations

from pathlib import Path

import pytest

from labelme import __appname__
from labelme import _app
from labelme import _automation


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


@pytest.mark.parametrize(
    "image_or_label_path, output_dir, expected",
    [
        (str(Path("/data/img.png")), None, str(Path("/data/img.json"))),
        (str(Path("/data/img.png")), Path("/out"), str(Path("/out/img.json"))),
        (str(Path("/data/foo.json")), None, str(Path("/data/foo.json"))),
        (str(Path("/data/foo.json")), Path("/out"), str(Path("/data/foo.json"))),
        (str(Path("/data/a.b.png")), None, str(Path("/data/a.b.json"))),
        (str(Path("/data/FOO.JSON")), None, str(Path("/data/FOO.JSON"))),
    ],
    ids=[
        "image-sibling-json",
        "image-honors-output-dir",
        "label-path-passthrough",
        "label-path-ignores-output-dir",
        "multi-dot-stem",
        "uppercase-suffix-passthrough",
    ],
)
def test_resolve_label_path(
    image_or_label_path: str,
    output_dir: Path | None,
    expected: str,
) -> None:
    assert (
        _app._resolve_label_path(
            image_or_label_path=image_or_label_path, output_dir=output_dir
        )
        == expected
    )
