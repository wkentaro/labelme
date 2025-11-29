from __future__ import annotations

import pathlib
from collections.abc import Generator
from typing import Literal

import pytest
from PyQt5 import QtWidgets
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QSettings
from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from pytestqt.qtbot import QtBot

import labelme.app
import labelme.config
import labelme.testing


@pytest.fixture(autouse=True)
def _isolated_qtsettings(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    settings_file = tmp_path / "qtsettings.ini"
    settings: QSettings = QSettings(str(settings_file), QSettings.IniFormat)
    monkeypatch.setattr(
        labelme.app.QtCore, "QSettings", lambda *args, **kwargs: settings
    )
    yield


def _show_window_and_wait_for_imagedata(
    qtbot: QtBot, win: labelme.app.MainWindow
) -> None:
    win.show()

    def check_imageData():
        assert hasattr(win, "imageData")
        assert win.imageData is not None

    qtbot.waitUntil(check_imageData)  # wait for loadFile


@pytest.mark.gui
def test_MainWindow_open(qtbot: QtBot) -> None:
    win: labelme.app.MainWindow = labelme.app.MainWindow()
    qtbot.addWidget(win)
    win.show()
    win.close()


@pytest.mark.gui
def test_MainWindow_open_img(qtbot: QtBot, data_path: pathlib.Path) -> None:
    image_file: str = str(data_path / "raw/2011_000003.jpg")
    win: labelme.app.MainWindow = labelme.app.MainWindow(filename=image_file)
    qtbot.addWidget(win)
    _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win.close()


@pytest.mark.gui
def test_MainWindow_open_json(qtbot: QtBot, data_path: pathlib.Path) -> None:
    json_files: list[str] = [
        str(data_path / "annotated_with_data/apc2016_obj3.json"),
        str(data_path / "annotated/2011_000003.json"),
    ]
    json_file: str
    for json_file in json_files:
        labelme.testing.assert_labelfile_sanity(json_file)

        win: labelme.app.MainWindow = labelme.app.MainWindow(filename=json_file)
        qtbot.addWidget(win)
        _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
        win.close()


@pytest.mark.gui
@pytest.mark.parametrize("scenario", ["raw", "annotated", "annotated_nested"])
def test_MainWindow_open_dir(
    qtbot: QtBot,
    scenario: Literal["raw", "annotated", "annotated_nested"],
    data_path: pathlib.Path,
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
    _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    first_image_name: str = "2011_000003.jpg"
    second_image_name: str = "2011_000006.jpg"

    assert win.imagePath
    assert pathlib.Path(win.imagePath).name == first_image_name
    win._open_prev_image()
    qtbot.wait(100)
    assert pathlib.Path(win.imagePath).name == first_image_name

    win._open_next_image()
    qtbot.wait(100)
    assert pathlib.Path(win.imagePath).name == second_image_name
    win._open_prev_image()
    qtbot.wait(100)
    assert pathlib.Path(win.imagePath).name == first_image_name

    assert win.fileListWidget.count() == 3
    expected_check_state = (
        Qt.Checked if scenario.startswith("annotated") else Qt.Unchecked
    )
    for index in range(win.fileListWidget.count()):
        item: QtWidgets.QListWidgetItem | None = win.fileListWidget.item(index)
        assert item
        assert item.checkState() == expected_check_state


@pytest.mark.gui
def test_MainWindow_annotate_jpg(
    qtbot: QtBot, data_path: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    input_file: str = str(data_path / "raw/2011_000003.jpg")
    out_file: str = str(tmp_path / "2011_000003.json")

    config: dict = labelme.config._get_default_config_and_create_labelmerc()
    win: labelme.app.MainWindow = labelme.app.MainWindow(
        config=config,
        filename=input_file,
        output_file=out_file,
    )
    qtbot.addWidget(win)
    _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label: str = "whole"
    canvas_size: QSize = win.canvas.size()
    points: list[tuple[float, float]] = [
        (canvas_size.width() * 0.25, canvas_size.height() * 0.25),
        (canvas_size.width() * 0.75, canvas_size.height() * 0.25),
        (canvas_size.width() * 0.75, canvas_size.height() * 0.75),
        (canvas_size.width() * 0.25, canvas_size.height() * 0.75),
    ]
    win._switch_canvas_mode(edit=False, createMode="polygon")
    qtbot.wait(100)

    def click(xy: tuple[float, float]) -> None:
        qtbot.mouseMove(win.canvas, pos=QPoint(int(xy[0]), int(xy[1])))
        qtbot.wait(100)
        qtbot.mousePress(win.canvas, Qt.LeftButton, pos=QPoint(int(xy[0]), int(xy[1])))
        qtbot.wait(100)

    [click(xy=xy) for xy in points]

    def interact() -> None:
        qtbot.keyClicks(win.labelDialog.edit, label)
        qtbot.wait(100)
        qtbot.keyClick(win.labelDialog.edit, Qt.Key_Enter)
        qtbot.wait(100)

    QTimer.singleShot(300, interact)

    click(xy=points[0])

    assert len(win.canvas.shapes) == 1
    assert len(win.canvas.shapes[0].points) == 4
    assert win.canvas.shapes[0].label == "whole"
    assert win.canvas.shapes[0].shape_type == "polygon"
    assert win.canvas.shapes[0].group_id is None
    assert win.canvas.shapes[0].mask is None
    assert win.canvas.shapes[0].flags == {}

    win.saveFile()

    labelme.testing.assert_labelfile_sanity(out_file)


@pytest.mark.gui
def test_image_navigation_while_selecting_shape(
    qtbot: QtBot, data_path: pathlib.Path
) -> None:
    win: labelme.app.MainWindow = labelme.app.MainWindow(
        filename=str(data_path / "annotated")
    )
    qtbot.addWidget(win)
    _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    # Incident: https://github.com/wkentaro/labelme/pull/1716 {{
    point = QPoint(250, 200)
    qtbot.mouseMove(win.canvas, pos=point)
    qtbot.mouseClick(win.canvas, Qt.LeftButton, pos=point)
    qtbot.wait(100)

    qtbot.mouseClick(win.fileListWidget, Qt.LeftButton)
    qtbot.wait(100)

    qtbot.keyClick(win.fileListWidget, Qt.Key_Down)
    qtbot.wait(100)
    qtbot.keyClick(win.canvas, Qt.Key_Down)
    qtbot.wait(100)
    # }}

    win.close()
