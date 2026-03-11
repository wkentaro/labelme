from __future__ import annotations

import json
import shutil
from pathlib import Path

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
    assert label_file.imagePath == "../images/2011_000003.jpg"
    assert label_file.imageData is not None
