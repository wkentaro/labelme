from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import imgviz
import pytest
from PyQt5.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

import labelme.utils


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--pause",
        action="store_true",
        default=False,
        help="Pause after each GUI test until the window is closed manually.",
    )
    parser.addoption(
        "--headed",
        action="store_true",
        default=False,
        help="Run GUI tests with a visible window (skip QT_QPA_PLATFORM=offscreen).",
    )


def pytest_configure(config: pytest.Config) -> None:
    if not config.getoption("--headed"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture()
def pause(request: pytest.FixtureRequest) -> bool:
    return request.config.getoption("--pause", default=False)


def assert_labelfile_sanity(filename: str) -> None:
    label_path = Path(filename)
    assert label_path.exists()

    with open(label_path) as f:
        data = json.load(f)

    assert "imagePath" in data
    image_data = data.get("imageData", None)
    if image_data is None:
        img_file = label_path.parent / data["imagePath"]
        assert img_file.exists()
        img = imgviz.io.imread(img_file)
    else:
        img = labelme.utils.img_b64_to_arr(image_data)

    height, width = img.shape[:2]
    assert height == data["imageHeight"]
    assert width == data["imageWidth"]

    assert "shapes" in data
    for shape in data["shapes"]:
        assert "label" in shape
        assert "points" in shape
        for x, y in shape["points"]:
            assert 0 <= x <= width
            assert 0 <= y <= height


def close_or_pause(
    *, qtbot: QtBot, widget: QWidget, pause: bool, timeout: int = 60_000
) -> None:
    if pause:
        qtbot.waitUntil(lambda: not widget.isVisible(), timeout=timeout)
    else:
        widget.close()


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
