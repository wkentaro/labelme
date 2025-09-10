import os.path as osp
import shutil
import tempfile

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from pytestqt.qtbot import QtBot

import labelme.app
import labelme.config
import labelme.testing

here = osp.dirname(osp.abspath(__file__))
data_dir = osp.join(here, "data")


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
def test_MainWindow_open_img(qtbot: QtBot) -> None:
    img_file: str = osp.join(data_dir, "raw/2011_000003.jpg")
    win: labelme.app.MainWindow = labelme.app.MainWindow(filename=img_file)
    qtbot.addWidget(win)
    _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win.close()


@pytest.mark.gui
def test_MainWindow_open_json(qtbot: QtBot):
    json_files: list[str] = [
        osp.join(data_dir, "annotated_with_data/apc2016_obj3.json"),
        osp.join(data_dir, "annotated/2011_000003.json"),
    ]
    json_file: str
    for json_file in json_files:
        labelme.testing.assert_labelfile_sanity(json_file)

        win: labelme.app.MainWindow = labelme.app.MainWindow(filename=json_file)
        qtbot.addWidget(win)
        _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
        win.close()


@pytest.mark.gui
def test_MainWindow_openNextAndPrevImg(qtbot: QtBot) -> None:
    directory: str = osp.join(data_dir, "raw")
    win: labelme.app.MainWindow = labelme.app.MainWindow(filename=directory)
    qtbot.addWidget(win)
    _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    first_image_name: str = "2011_000003.jpg"
    second_image_name: str = "2011_000006.jpg"

    assert osp.basename(win.imagePath) == first_image_name
    win.openPrevImg()
    qtbot.wait(100)
    assert osp.basename(win.imagePath) == first_image_name

    win.openNextImg()
    qtbot.wait_until(lambda: osp.basename(win.imagePath) != first_image_name)
    assert osp.basename(win.imagePath) == second_image_name
    win.openPrevImg()
    qtbot.wait_until(lambda: osp.basename(win.imagePath) != second_image_name)
    assert osp.basename(win.imagePath) == first_image_name


@pytest.mark.gui
def test_MainWindow_annotate_jpg(qtbot: QtBot) -> None:
    tmp_dir: str = tempfile.mkdtemp()
    input_file: str = osp.join(data_dir, "raw/2011_000003.jpg")
    out_file: str = osp.join(tmp_dir, "2011_000003.json")

    config: dict = labelme.config._get_default_config_and_create_labelmerc()
    win: labelme.app.MainWindow = labelme.app.MainWindow(
        config=config,
        filename=input_file,
        output_file=out_file,
    )
    qtbot.addWidget(win)
    _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label: str = "whole"
    points: list[tuple[float, float]] = [
        (100, 100),
        (100, 238),
        (400, 238),
        (400, 100),
    ]
    win.toggleDrawMode(edit=False, createMode="polygon")
    qtbot.wait(100)

    def click(xy: tuple[float, float]) -> None:
        qtbot.mouseMove(win.canvas, pos=QPoint(*xy))
        qtbot.wait(100)
        qtbot.mousePress(win.canvas, Qt.LeftButton, pos=QPoint(*xy))
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
    shutil.rmtree(tmp_dir)
