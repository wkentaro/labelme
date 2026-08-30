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
    *,
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
    *,
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
    *,
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

    annotation_before = win._annotation
    win._load_from_file_or_dir(file_or_dir=directory)
    qtbot.waitUntil(lambda: win._annotation is not annotation_before)
    assert win._docks.file_list.currentRow() == 0

    win._open_prev_image()
    qtbot.wait(100)
    assert Path(win._image_path).name == first_image_name

    win._open_next_image()
    qtbot.wait(100)
    assert Path(win._image_path).name == second_image_name
    win._open_prev_image()
    qtbot.wait(100)
    assert Path(win._image_path).name == first_image_name

    win._open_next_image()
    qtbot.waitUntil(lambda: Path(win._image_path or "").name == second_image_name)
    win._load_from_file_or_dir(file_or_dir=directory)
    qtbot.waitUntil(lambda: Path(win._image_path or "").name == first_image_name)
    assert win._docks.file_list.currentRow() == 0

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
def test_reopening_directory_preserves_session_when_first_image_fails(
    main_win: MainWinFactory,
    qtbot: QtBot,
    create_annotated_session_image: Path,
    critical_messages: list[str],
    *,
    pause: bool,
) -> None:
    current_image = create_annotated_session_image
    win = main_win(file_or_dir=current_image.parent)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    annotation_before = win._annotation
    current_item_before = win._docks.file_list.currentItem()
    assert current_item_before is not None
    current_path_before = current_item_before.text()

    current_image.write_bytes(b"not an image")
    win._load_from_file_or_dir(file_or_dir=str(current_image.parent))

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._annotation is annotation_before
    current_item = win._docks.file_list.currentItem()
    assert current_item is not None
    assert current_item.text() == current_path_before
    assert win._docks.file_list.currentRow() == 0

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_MainWindow_reports_size_when_image_exceeds_decode_limit(
    raw_win: MainWindow,
    qtbot: QtBot,
    tmp_path: Path,
    critical_messages: list[str],
    set_allocation_limit: Callable[[int], None],
    *,
    pause: bool,
) -> None:
    image_path = tmp_path / "too_large.png"
    image = QtGui.QImage(800, 600, QtGui.QImage.Format.Format_RGB32)
    image.fill(0)
    assert image.save(str(image_path))

    set_allocation_limit(1)

    raw_win._load_file(image_or_label_path=str(image_path))

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
    raw_win._load_file(image_or_label_path=str(label_path))

    assert len(critical_messages) == 1
    assert str(label_path) in critical_messages[0]
    assert "shapes[1]" in critical_messages[0]
    assert error_field in critical_messages[0]
    assert raw_win._canvas_widgets.canvas.shapes == []
    assert len(raw_win._docks.label_list) == 0


@pytest.fixture
def create_annotated_session_image(data_path: Path, tmp_path: Path) -> Path:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    image_path = session_dir / "01-current.jpg"
    shutil.copyfile(
        src=data_path / "annotated/2011_000003.jpg",
        dst=image_path,
    )
    annotation_data = json.loads((data_path / "annotated/2011_000003.json").read_text())
    annotation_data["imagePath"] = image_path.name
    image_path.with_suffix(".json").write_text(json.dumps(annotation_data))
    return image_path


@pytest.fixture
def choose_candidate_output_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(candidate_dir),
    )
    return candidate_dir


@pytest.mark.gui
@pytest.mark.parametrize(
    ("failure", "navigation"),
    [
        ("missing_image", "next"),
        ("unreadable_image", "next"),
        ("unreadable_tiff", "open_file"),
        ("corrupt_annotation", "next"),
        ("corrupt_annotation", "open_file"),
        ("semantically_invalid_annotation", "next"),
    ],
)
def test_failed_navigation_preserves_current_session(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    create_annotated_session_image: Path,
    critical_messages: list[str],
    *,
    pause: bool,
    failure: str,
    navigation: str,
) -> None:
    source_image = data_path / "annotated/2011_000003.jpg"
    current_image = create_annotated_session_image
    session_dir = current_image.parent
    current_annotation = session_dir / "01-current.json"
    next_suffix = ".tiff" if failure == "unreadable_tiff" else ".jpg"
    next_image = session_dir / f"02-next{next_suffix}"
    next_annotation = session_dir / "02-next.json"

    current_annotation_data = json.loads(current_annotation.read_text())

    if failure == "unreadable_tiff":
        next_image.write_bytes(b"II*\x00")
    elif failure == "unreadable_image":
        next_image.write_bytes(b"not an image")
    else:
        shutil.copyfile(src=source_image, dst=next_image)
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


@pytest.mark.gui
def test_failed_navigation_restores_selected_source_item(
    main_win: MainWinFactory,
    qtbot: QtBot,
    create_annotated_session_image: Path,
    critical_messages: list[str],
    *,
    pause: bool,
) -> None:
    current_image = create_annotated_session_image
    current_annotation = current_image.with_suffix(".json")
    annotation_data = json.loads(current_annotation.read_text())
    annotation_data["imagePath"] = current_image.name.upper()
    annotation_data["imageData"] = base64.b64encode(current_image.read_bytes()).decode()
    current_annotation.write_text(json.dumps(annotation_data))
    next_image = current_image.parent / "02-next.jpg"
    next_image.write_bytes(b"not an image")

    win = main_win(file_or_dir=current_image.parent)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert win._image_path != str(current_image)

    win._open_next_image()

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    current_item = win._docks.file_list.currentItem()
    assert current_item is not None
    assert current_item.text() == str(current_image)
    assert win._docks.file_list.currentRow() == 0
    assert "[1/2]" in win.windowTitle()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_direct_image_open_preserves_source_selection(
    main_win: MainWinFactory,
    qtbot: QtBot,
    create_annotated_session_image: Path,
    *,
    pause: bool,
) -> None:
    current_image = create_annotated_session_image
    direct_image = current_image.parent / "02-direct.jpg"
    shutil.copyfile(src=current_image, dst=direct_image)
    direct_annotation = direct_image.with_suffix(".json")
    annotation_data = json.loads(current_image.with_suffix(".json").read_text())
    annotation_data["imagePath"] = direct_image.name.upper()
    annotation_data["imageData"] = base64.b64encode(direct_image.read_bytes()).decode()
    direct_annotation.write_text(json.dumps(annotation_data))

    win = main_win(file_or_dir=current_image.parent)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._load_from_file_or_dir(file_or_dir=str(direct_image))

    current_item = win._docks.file_list.currentItem()
    assert current_item is not None
    assert current_item.text() == str(direct_image)
    assert win._docks.file_list.currentRow() == 1
    assert "[2/2]" in win.windowTitle()
    assert win._image_path != str(direct_image)

    win._docks.file_search.setText(r"02-direct\.jpg$")
    current_item = win._docks.file_list.currentItem()
    assert current_item is not None
    assert current_item.text() == str(direct_image)
    assert "[1/1]" in win.windowTitle()

    win._docks.file_search.clear()
    assert win._docks.file_list.currentRow() == 1
    assert "[2/2]" in win.windowTitle()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_failed_navigation_restores_filtered_out_selection(
    main_win: MainWinFactory,
    qtbot: QtBot,
    create_annotated_session_image: Path,
    critical_messages: list[str],
    *,
    pause: bool,
) -> None:
    current_image = create_annotated_session_image
    next_image = current_image.parent / "02-next.jpg"
    shutil.copyfile(src=current_image, dst=next_image)

    win = main_win(file_or_dir=current_image.parent)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    next_image.unlink()
    win._docks.file_search.setText(r"02-next\.jpg$")
    assert win._docks.file_list.currentItem() is None

    win._docks.file_list.setCurrentRow(0)

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._image_path == str(current_image)
    assert win._docks.file_list.currentItem() is None
    assert win._docks.file_list.currentRow() == -1

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_failed_navigation_refreshes_title_after_saving(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    create_annotated_session_image: Path,
    critical_messages: list[str],
    *,
    pause: bool,
) -> None:
    current_image = create_annotated_session_image
    next_image = current_image.parent / "02-next.jpg"
    next_image.write_bytes(b"not an image")
    win = main_win(
        file_or_dir=current_image.parent,
        config_overrides={"auto_save": False},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win.mark_dirty()
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.StandardButton.Save,
    )

    win._open_next_image()

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._docks.file_list.currentRow() == 0
    assert "[1/2]" in win.windowTitle()
    assert not win.windowTitle().endswith("*")

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("hide_active_image", [False, True])
def test_prompt_output_dir_rejects_corrupt_annotation(
    main_win: MainWinFactory,
    qtbot: QtBot,
    create_annotated_session_image: Path,
    choose_candidate_output_dir: Path,
    critical_messages: list[str],
    *,
    pause: bool,
    hide_active_image: bool,
) -> None:
    current_image = create_annotated_session_image
    candidate_dir = choose_candidate_output_dir
    candidate_annotation = candidate_dir / current_image.with_suffix(".json").name
    candidate_annotation.write_text("{")
    win = main_win(file_or_dir=current_image.parent)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    if hide_active_image:
        win._docks.file_search.setText(r"does-not-match$")

    annotation_before = win._annotation
    pixmap_cache_key_before = win._canvas_widgets.canvas.pixmap.cacheKey()
    title_before = win.windowTitle()
    current_item_before = win._docks.file_list.currentItem()
    win.prompt_output_dir()

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._output_dir is None
    assert win._annotation is annotation_before
    assert win._canvas_widgets.canvas.pixmap.cacheKey() == pixmap_cache_key_before
    assert win._label_file_path == str(current_image.with_suffix(".json"))
    assert win._docks.file_list.currentItem() is current_item_before
    assert win.windowTitle() == title_before
    assert candidate_annotation.read_text() == "{"

    win.mark_dirty()
    assert candidate_annotation.read_text() == "{"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_prompt_output_dir_loads_candidate_before_committing(
    main_win: MainWinFactory,
    qtbot: QtBot,
    create_annotated_session_image: Path,
    choose_candidate_output_dir: Path,
    *,
    pause: bool,
) -> None:
    current_image = create_annotated_session_image
    current_annotation = current_image.with_suffix(".json")
    candidate_dir = choose_candidate_output_dir
    candidate_annotation = candidate_dir / current_annotation.name
    annotation_data = json.loads(current_annotation.read_text())
    annotation_data["imageData"] = base64.b64encode(current_image.read_bytes()).decode()
    annotation_data["candidateMarker"] = True
    candidate_annotation.write_text(json.dumps(annotation_data))

    win = main_win(file_or_dir=current_image.parent)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    current_annotation.unlink()
    win._refresh_file_list()
    current_item = win._docks.file_list.currentItem()
    assert current_item is not None
    assert current_item.checkState() == Qt.CheckState.Unchecked
    win.prompt_output_dir()

    assert win._output_dir == candidate_dir
    assert win._label_file_path == str(candidate_annotation)
    assert win._annotation is not None
    assert win._annotation.other_data["candidateMarker"] is True
    current_item = win._docks.file_list.currentItem()
    assert current_item is not None
    assert current_item.checkState() == Qt.CheckState.Checked

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_failed_load_of_dropped_image_preserves_current_session(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    create_annotated_session_image: Path,
    critical_messages: list[str],
    *,
    pause: bool,
) -> None:
    current_image = create_annotated_session_image
    session_dir = current_image.parent
    existing_image = session_dir / "02-existing.jpg"
    shutil.copyfile(
        src=data_path / "raw/2011_000006.jpg",
        dst=existing_image,
    )

    win = main_win(file_or_dir=session_dir)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    annotation_before = win._annotation

    win.import_dropped_image_files([str(existing_image)])
    assert win._image_path == str(current_image)

    corrupt_image = tmp_path / "dropped.jpg"
    corrupt_image.write_bytes(b"not an image")
    win.import_dropped_image_files([str(corrupt_image)])

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._image_path == str(current_image)
    assert win._annotation is annotation_before
    assert win._canvas_widgets.canvas.isEnabled()
    assert win._docks.file_list.currentRow() == 0
    assert str(corrupt_image) in critical_messages[0]

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_open_dir_with_failing_first_image_keeps_other_images_reachable(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    create_annotated_session_image: Path,
    critical_messages: list[str],
    *,
    pause: bool,
) -> None:
    current_image = create_annotated_session_image
    session_dir = current_image.parent

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    corrupt_image = other_dir / "01-corrupt.jpg"
    corrupt_image.write_bytes(b"not an image")
    valid_image = other_dir / "02-valid.jpg"
    shutil.copyfile(src=data_path / "raw/2011_000003.jpg", dst=valid_image)

    win = main_win(file_or_dir=session_dir)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    annotation_before = win._annotation

    win._load_from_file_or_dir(file_or_dir=str(other_dir))

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    # The directory swap itself succeeds; the previous session stays alive
    # until a load succeeds, and the remaining images stay reachable.
    assert win.image_list == [str(corrupt_image), str(valid_image)]
    assert win._annotation is annotation_before
    assert win._docks.file_list.currentItem() is None

    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: win._image_path == str(valid_image))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
