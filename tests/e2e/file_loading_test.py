from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

import labelme.app
import labelme.testing

from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_MainWindow_open_img(
    qtbot: QtBot,
    data_path: Path,
) -> None:
    image_file: str = str(data_path / "raw/2011_000003.jpg")
    win: labelme.app.MainWindow = labelme.app.MainWindow(filename=image_file)
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win.close()


@pytest.mark.gui
def test_MainWindow_open_json(
    qtbot: QtBot,
    data_path: Path,
) -> None:
    json_files: list[str] = [
        str(data_path / "annotated_with_data/apc2016_obj3.json"),
        str(data_path / "annotated/2011_000003.json"),
    ]
    json_file: str
    for json_file in json_files:
        labelme.testing.assert_labelfile_sanity(json_file)

        win: labelme.app.MainWindow = labelme.app.MainWindow(filename=json_file)
        qtbot.addWidget(win)
        show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
        win.close()


@pytest.mark.gui
@pytest.mark.parametrize("scenario", ["raw", "annotated", "annotated_nested"])
def test_MainWindow_open_dir(
    qtbot: QtBot,
    scenario: Literal["raw", "annotated", "annotated_nested"],
    data_path: Path,
) -> None:
    directory: str
    output_dir: str | None
    if scenario == "annotated_nested":
        directory = str(data_path / "annotated_nested" / "images")
        output_dir = str(data_path / "annotated_nested" / "annotations")
    else:
        directory = str(data_path / scenario)
        output_dir = None

    win: labelme.app.MainWindow = labelme.app.MainWindow(
        filename=directory, output_dir=output_dir
    )
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    first_image_name: str = "2011_000003.jpg"
    second_image_name: str = "2011_000006.jpg"

    assert win.imagePath
    assert Path(win.imagePath).name == first_image_name
    win._open_prev_image()
    qtbot.wait(100)
    assert Path(win.imagePath).name == first_image_name

    win._open_next_image()
    qtbot.wait(100)
    assert Path(win.imagePath).name == second_image_name
    win._open_prev_image()
    qtbot.wait(100)
    assert Path(win.imagePath).name == first_image_name

    assert win.fileListWidget.count() == 3
    expected_check_state = (
        Qt.Checked if scenario.startswith("annotated") else Qt.Unchecked
    )
    for index in range(win.fileListWidget.count()):
        item: QtWidgets.QListWidgetItem | None = win.fileListWidget.item(index)
        assert item
        assert item.checkState() == expected_check_state
