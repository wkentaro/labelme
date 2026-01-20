import json
import shutil
from pathlib import Path

import pytest


def _create_annotated_nested(data_path: Path) -> None:
    dst_dir: Path = data_path / "annotated_nested"
    dst_dir.mkdir()

    (dst_dir / "images").mkdir()
    for image_file in (data_path / "annotated").glob("*.jpg"):
        shutil.copy(image_file, dst_dir / "images" / image_file.name)

    (dst_dir / "annotations").mkdir()
    for json_file in (data_path / "annotated").glob("*.json"):
        dst_json_file = dst_dir / "annotations" / json_file.name
        shutil.copy(json_file, dst_json_file)
        with open(dst_json_file) as f:
            json_data = json.load(f)
        json_data["imagePath"] = str(Path("..") / "images" / json_data["imagePath"])
        with open(dst_json_file, "w") as f:
            json.dump(json_data, f, indent=2)


@pytest.fixture(scope="function")
def data_path(tmp_path: Path) -> Path:
    data_path: Path = tmp_path / "data"
    shutil.copytree(Path(__file__).parent / "data", data_path)

    _create_annotated_nested(data_path=data_path)

    return data_path
