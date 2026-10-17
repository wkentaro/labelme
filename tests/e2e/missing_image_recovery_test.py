from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Final

import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause

_RAW_FILE_NAME: Final[str] = "raw/2011_000003.jpg"


@pytest.mark.gui
def test_locate_replacement_image_recovers_session_marks_dirty_and_saves(
    *,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    # 1. Establish an active valid session
    raw_win._load_file(image_or_label_path=str(data_path / _RAW_FILE_NAME))
    qtbot.waitUntil(lambda: raw_win._annotation is not None, timeout=5_000)
    assert not raw_win._is_changed

    # 2. Prepare a replacement image and a JSON pointing to a missing image
    replacement_img = tmp_path / "replacement.jpg"
    shutil.copy(data_path / _RAW_FILE_NAME, replacement_img)

    json_path = tmp_path / "missing_target.json"
    raw_json = {
        "version": "6.0.0",
        "flags": {},
        "shapes": [
            {
                "label": "recovered_box",
                "points": [[10.0, 10.0], [50.0, 50.0]],
                "shape_type": "rectangle",
            }
        ],
        "imagePath": "absent_image.jpg",
        "imageData": None,
        "imageHeight": 338,
        "imageWidth": 500,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw_json, f)

    # 3. Intercept modal dialog: click Locate Image, then mock file chooser
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(replacement_img), "Images (*)"),
    )

    def on_modal() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        locate_btn = next(b for b in dialog.buttons() if "Locate Image" in b.text())
        locate_btn.click()

    QTimer.singleShot(0, on_modal)
    loaded = raw_win._load_file(image_or_label_path=str(json_path))
    assert loaded is True

    # 4. Verify recovery state: loaded in session, marked dirty, file on disk unchanged
    assert raw_win._is_changed is True
    assert raw_win.windowTitle().endswith("*")
    assert raw_win._image_path == str(replacement_img)
    assert len(raw_win._canvas_widgets.canvas.shapes) == 1
    assert raw_win._canvas_widgets.canvas.shapes[0].label == "recovered_box"

    # Crucial acceptance criterion: annotation file on disk is NOT mutated
    disk_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert disk_data["imagePath"] == "absent_image.jpg"

    # 5. Persist the repaired reference explicitly
    saved = raw_win.save_labels(label_path=str(json_path))
    assert saved is True
    assert raw_win._is_changed is False
    assert not raw_win.windowTitle().endswith("*")

    saved_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved_data["imagePath"] == "replacement.jpg"

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_locate_replacement_image_cancelled_file_dialog_preserves_session(
    *,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    # 1. Establish an active valid session
    initial_image_path = str(data_path / _RAW_FILE_NAME)
    raw_win._load_file(image_or_label_path=initial_image_path)
    qtbot.waitUntil(lambda: raw_win._annotation is not None, timeout=5_000)
    initial_annotation = raw_win._annotation

    # 2. Prepare JSON pointing to missing image
    json_path = tmp_path / "missing_target.json"
    raw_json = {
        "version": "6.0.0",
        "flags": {},
        "shapes": [],
        "imagePath": "absent_image.jpg",
        "imageData": None,
        "imageHeight": 338,
        "imageWidth": 500,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw_json, f)

    # User clicks Locate Image, but cancels file dialog
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: ("", ""),
    )

    def on_modal() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        locate_btn = next(b for b in dialog.buttons() if "Locate Image" in b.text())
        locate_btn.click()

    QTimer.singleShot(0, on_modal)
    loaded = raw_win._load_file(image_or_label_path=str(json_path))
    assert loaded is False

    # 3. Verify previous session was preserved
    assert raw_win._image_path == initial_image_path
    assert raw_win._annotation is initial_annotation
    assert raw_win._is_changed is False

    # Annotation file on disk is unchanged
    disk_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert disk_data["imagePath"] == "absent_image.jpg"

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_locate_replacement_image_cancelled_dialog_preserves_session(
    *,
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    # 1. Establish active valid session
    initial_image_path = str(data_path / _RAW_FILE_NAME)
    raw_win._load_file(image_or_label_path=initial_image_path)
    qtbot.waitUntil(lambda: raw_win._annotation is not None, timeout=5_000)
    initial_annotation = raw_win._annotation

    # 2. Prepare JSON pointing to missing image
    json_path = tmp_path / "missing_target.json"
    raw_json = {
        "version": "6.0.0",
        "flags": {},
        "shapes": [],
        "imagePath": "absent_image.jpg",
        "imageData": None,
        "imageHeight": 338,
        "imageWidth": 500,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw_json, f)

    def on_modal() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        dialog.reject()

    QTimer.singleShot(0, on_modal)
    loaded = raw_win._load_file(image_or_label_path=str(json_path))
    assert loaded is False

    # 3. Verify previous session was preserved
    assert raw_win._image_path == initial_image_path
    assert raw_win._annotation is initial_annotation
    assert raw_win._is_changed is False

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)
