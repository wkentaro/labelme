import os.path as osp
import shutil
import tempfile

import pytest
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


def _create_window_with_directory(qtbot: QtBot) -> labelme.app.MainWindow:
    directory: str = osp.join(data_dir, "raw")
    win: labelme.app.MainWindow = labelme.app.MainWindow(filename=directory)
    qtbot.addWidget(win)
    _show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


@pytest.mark.gui
def test_MainWindow_openNextImg(qtbot: QtBot) -> None:
    win: labelme.app.MainWindow = _create_window_with_directory(qtbot=qtbot)
    win.openNextImg()


@pytest.mark.gui
def test_MainWindow_openPrevImg(qtbot: QtBot) -> None:
    win: labelme.app.MainWindow = _create_window_with_directory(qtbot=qtbot)
    win.openNextImg()


@pytest.mark.gui
def test_MainWindow_annotate_jpg(qtbot: QtBot) -> None:
    tmp_dir: str = tempfile.mkdtemp()
    input_file: str = osp.join(data_dir, "raw/2011_000003.jpg")
    out_file: str = osp.join(tmp_dir, "2011_000003.json")

    config: dict = labelme.config.get_default_config()
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
    shapes: list[dict] = [
        dict(
            label=label,
            group_id=None,
            points=points,
            shape_type="polygon",
            mask=None,
            flags={},
            other_data={},
        )
    ]
    win.loadLabels(shapes)
    win.saveFile()

    labelme.testing.assert_labelfile_sanity(out_file)
    shutil.rmtree(tmp_dir)
