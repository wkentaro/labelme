from __future__ import annotations

import base64
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_MainWindow_open_img(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    image_file: str = str(data_path / "raw/2011_000003.jpg")
    win = main_win(file_or_dir=image_file)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_MainWindow_open_json(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    json_files: list[str] = [
        str(data_path / "annotated_with_data/apc2016_obj3.json"),
        str(data_path / "annotated/2011_000003.json"),
    ]
    json_file: str
    for json_file in json_files:
        assert_labelfile_sanity(json_file)

        win = main_win(file_or_dir=json_file)
        show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
        assert "[" not in win.windowTitle()

        close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("scenario", ["raw", "annotated", "annotated_nested"])
def test_MainWindow_open_dir(
    main_win: MainWinFactory,
    qtbot: QtBot,
    scenario: Literal["raw", "annotated", "annotated_nested"],
    data_path: Path,
    pause: bool,
) -> None:
    directory: str
    output_dir: str | None
    if scenario == "annotated_nested":
        directory = str(data_path / "annotated_nested" / "images")
        output_dir = str(data_path / "annotated_nested" / "annotations")
    else:
        directory = str(data_path / scenario)
        output_dir = None

    win = main_win(file_or_dir=directory, output_dir=output_dir)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    first_image_name: str = "2011_000003.jpg"
    second_image_name: str = "2011_000006.jpg"

    assert win._image_path
    assert Path(win._image_path).name == first_image_name
    assert "[1/3]" in win.windowTitle()
    win._open_prev_image()
    qtbot.wait(100)
    assert Path(win._image_path).name == first_image_name

    win._open_next_image()
    qtbot.wait(100)
    assert Path(win._image_path).name == second_image_name
    win._open_prev_image()
    qtbot.wait(100)
    assert Path(win._image_path).name == first_image_name

    assert win._docks.file_list.count() == 3
    expected_check_state = (
        Qt.CheckState.Checked
        if scenario.startswith("annotated")
        else Qt.CheckState.Unchecked
    )
    for index in range(win._docks.file_list.count()):
        item: QtWidgets.QListWidgetItem | None = win._docks.file_list.item(index)
        assert item
        assert item.checkState() == expected_check_state

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_MainWindow_reports_size_when_image_exceeds_decode_limit(
    raw_win: MainWindow,
    qtbot: QtBot,
    tmp_path: Path,
    critical_messages: list[str],
    set_allocation_limit: Callable[[int], None],
    pause: bool,
) -> None:
    image_path = tmp_path / "too_large.png"
    image = QtGui.QImage(800, 600, QtGui.QImage.Format.Format_RGB32)
    image.fill(0)
    assert image.save(str(image_path))

    set_allocation_limit(1)

    raw_win._load_file(str(image_path))

    assert len(critical_messages) == 1
    assert "800x600" in critical_messages[0]
    assert "1 MB" in critical_messages[0]
    assert "gdal_retile.py" in critical_messages[0]
    assert "Allowed formats" not in critical_messages[0]

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("invalid_shape", "error_field"),
    [
        (
            {
                "label": "unknown",
                "points": [[0.0, 0.0]],
                "shape_type": "triangle",
            },
            "shape_type",
        ),
        (
            {
                "label": "rectangle",
                "points": [[0.0, 0.0]],
                "shape_type": "rectangle",
            },
            "points",
        ),
        (
            {
                "label": "mask",
                "points": [[0.0, 0.0], [1.0, 1.0]],
                "shape_type": "mask",
            },
            "mask",
        ),
    ],
    ids=["unknown-shape-type", "invalid-point-count", "missing-mask"],
)
def test_MainWindow_rejects_malformed_shapes_before_installing_any(
    raw_win: MainWindow,
    critical_messages: list[str],
    data_path: Path,
    tmp_path: Path,
    invalid_shape: dict[str, object],
    error_field: str,
) -> None:
    image_path = data_path / "raw/2011_000003.jpg"
    label_path = tmp_path / "malformed.json"
    label_path.write_text(
        json.dumps(
            {
                "version": "7.0.0",
                "flags": {},
                "shapes": [
                    {
                        "label": "valid",
                        "points": [[0.0, 0.0]],
                        "shape_type": "point",
                    },
                    invalid_shape,
                ],
                "imagePath": image_path.name,
                "imageData": base64.b64encode(image_path.read_bytes()).decode(),
            }
        )
    )
    raw_win._load_file(str(label_path))

    assert len(critical_messages) == 1
    assert str(label_path) in critical_messages[0]
    assert "shapes[1]" in critical_messages[0]
    assert error_field in critical_messages[0]
    assert raw_win._canvas_widgets.canvas.shapes == []
    assert len(raw_win._docks.label_list) == 0


@pytest.mark.gui
@pytest.mark.parametrize(
    ("failure", "navigation"),
    [
        ("missing_image", "next"),
        ("unreadable_image", "next"),
        ("corrupt_annotation", "next"),
        ("corrupt_annotation", "open_file"),
        ("semantically_invalid_annotation", "next"),
    ],
)
def test_failed_navigation_preserves_current_session(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    critical_messages: list[str],
    pause: bool,
    failure: str,
    navigation: str,
) -> None:
    source_image = data_path / "annotated/2011_000003.jpg"
    source_annotation = data_path / "annotated/2011_000003.json"
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    current_image = session_dir / "01-current.jpg"
    current_annotation = session_dir / "01-current.json"
    next_image = session_dir / "02-next.jpg"
    next_annotation = session_dir / "02-next.json"

    shutil.copyfile(source_image, current_image)
    current_annotation_data = json.loads(source_annotation.read_text())
    current_annotation_data["imagePath"] = current_image.name
    current_annotation.write_text(json.dumps(current_annotation_data))

    if failure == "unreadable_image":
        next_image.write_bytes(b"not an image")
    else:
        shutil.copyfile(source_image, next_image)
    if failure == "corrupt_annotation":
        next_annotation.write_text("{")
    elif failure == "semantically_invalid_annotation":
        invalid_annotation_data = dict(current_annotation_data)
        invalid_annotation_data["imagePath"] = next_image.name
        invalid_annotation_data["shapes"] = [
            dict(current_annotation_data["shapes"][0], shape_type="unsupported")
        ]
        next_annotation.write_text(json.dumps(invalid_annotation_data))

    win = main_win(file_or_dir=session_dir)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    if failure == "missing_image":
        next_image.unlink()

    canvas = win._canvas_widgets.canvas
    annotation_before = win._annotation
    image_cache_key_before = win._image.cacheKey()
    pixmap_cache_key_before = canvas.pixmap.cacheKey()
    shapes_before = canvas.shapes[:]
    row_before = win._docks.file_list.currentRow()

    if navigation == "open_file":
        win._load_from_file_or_dir(file_or_dir=str(next_image))
    else:
        win._open_next_image()

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._image_path == str(current_image)
    assert win._label_file_path == str(current_annotation)
    assert win._annotation is annotation_before
    assert win._image.cacheKey() == image_cache_key_before
    assert canvas.pixmap.cacheKey() == pixmap_cache_key_before
    assert len(canvas.shapes) == len(shapes_before)
    assert all(
        actual is expected for actual, expected in zip(canvas.shapes, shapes_before)
    )
    assert canvas.isEnabled()
    assert win._docks.file_list.currentRow() == row_before
    current_item = win._docks.file_list.currentItem()
    assert current_item is not None
    assert current_item.text() == str(current_image)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
