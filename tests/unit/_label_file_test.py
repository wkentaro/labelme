from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from labelme._label_file import LabelFile
from labelme._label_file import _load_shape_json_obj


def test_LabelFile_load_windows_path(data_path: Path, tmp_path: Path) -> None:
    """Test that LabelFile can load JSON with Windows-style backslash paths.

    Regression test for https://github.com/wkentaro/labelme/issues/1725
    """
    (tmp_path / "images").mkdir()
    shutil.copy(
        data_path / "annotated" / "2011_000003.jpg",
        tmp_path / "images" / "2011_000003.jpg",
    )

    json_file = tmp_path / "annotations" / "2011_000003.json"
    json_file.parent.mkdir()
    with open(data_path / "annotated" / "2011_000003.json") as f:
        json_data = json.load(f)
    json_data["imagePath"] = "..\\images\\2011_000003.jpg"
    with open(json_file, "w") as f:
        json.dump(json_data, f)

    label_file = LabelFile(str(json_file))
    assert label_file.imagePath == "../images/2011_000003.jpg"
    assert label_file.imageData is not None


# ---------------------------------------------------------------------------
# Tests for _load_shape_json_obj error paths and happy paths
# ---------------------------------------------------------------------------

_MINIMAL_VALID_SHAPE: dict = {
    "label": "cat",
    "points": [[10.0, 20.0], [30.0, 40.0]],
    "shape_type": "polygon",
}


def test_load_shape_missing_label() -> None:
    """Missing 'label' key must raise an error."""
    shape = {
        "points": [[10.0, 20.0]],
        "shape_type": "polygon",
    }
    # Accepts AssertionError (current code) or ValueError (after PR #1835 merge)
    with pytest.raises((AssertionError, ValueError)):
        _load_shape_json_obj(shape)


def test_load_shape_invalid_label_type() -> None:
    """Non-string label must raise an error."""
    shape = {
        "label": 42,
        "points": [[10.0, 20.0]],
        "shape_type": "polygon",
    }
    with pytest.raises((AssertionError, TypeError, ValueError)):
        _load_shape_json_obj(shape)


def test_load_shape_invalid_points_empty() -> None:
    """Empty points list must raise an error."""
    shape = {
        "label": "cat",
        "points": [],
        "shape_type": "polygon",
    }
    with pytest.raises((AssertionError, ValueError)):
        _load_shape_json_obj(shape)


def test_load_shape_invalid_points_type() -> None:
    """Points given as a string instead of a list must raise an error."""
    shape = {
        "label": "cat",
        "points": "[[10, 20]]",
        "shape_type": "polygon",
    }
    with pytest.raises((AssertionError, TypeError, ValueError)):
        _load_shape_json_obj(shape)


def test_load_shape_missing_shape_type() -> None:
    """Missing 'shape_type' key must raise an error."""
    shape = {
        "label": "cat",
        "points": [[10.0, 20.0]],
    }
    with pytest.raises((AssertionError, ValueError)):
        _load_shape_json_obj(shape)


def test_load_shape_valid_minimal() -> None:
    """Minimal valid shape dict should load without error."""
    result = _load_shape_json_obj(_MINIMAL_VALID_SHAPE)
    assert result["label"] == "cat"
    assert result["points"] == [[10.0, 20.0], [30.0, 40.0]]
    assert result["shape_type"] == "polygon"
    assert result["flags"] == {}
    assert result["description"] == ""
    assert result["group_id"] is None
    assert result["mask"] is None
    assert result["other_data"] == {}


def test_load_shape_other_data_passthrough() -> None:
    """Unknown keys in shape JSON should be collected in 'other_data'."""
    shape = {
        **_MINIMAL_VALID_SHAPE,
        "custom_field": "hello",
        "score": 0.95,
    }
    result = _load_shape_json_obj(shape)
    assert result["other_data"] == {"custom_field": "hello", "score": 0.95}
    # Known keys must NOT appear in other_data
    assert "label" not in result["other_data"]
    assert "points" not in result["other_data"]
