from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from labelme._label_file import LabelFile


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
    assert label_file.image_path == "../images/2011_000003.jpg"
    assert label_file.image_data is not None


def test_LabelFile_imagePath_deprecation() -> None:
    label_file = LabelFile()
    label_file.image_path = "foo.jpg"

    with pytest.warns(DeprecationWarning, match="image_path"):
        assert label_file.imagePath == "foo.jpg"

    with pytest.warns(DeprecationWarning, match="image_path"):
        label_file.imagePath = "bar.jpg"
    assert label_file.image_path == "bar.jpg"


def test_LabelFile_imageData_deprecation() -> None:
    label_file = LabelFile()
    label_file.image_data = b"foo"

    with pytest.warns(DeprecationWarning, match="image_data"):
        assert label_file.imageData == b"foo"

    with pytest.warns(DeprecationWarning, match="image_data"):
        label_file.imageData = b"bar"
    assert label_file.image_data == b"bar"


def test_LabelFile_otherData_deprecation() -> None:
    label_file = LabelFile()
    label_file.other_data = {"foo": 1}

    with pytest.warns(DeprecationWarning, match="other_data"):
        assert label_file.otherData == {"foo": 1}

    with pytest.warns(DeprecationWarning, match="other_data"):
        label_file.otherData = {"bar": 2}
    assert label_file.other_data == {"bar": 2}
