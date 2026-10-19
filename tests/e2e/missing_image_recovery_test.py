from __future__ import annotations

import json
import shutil
import struct
import zlib
from pathlib import Path
from typing import Final

import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
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


def _recover_annotation(
    *,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    absolute: bool,
    open_via_image: bool,
) -> tuple[Path, Path, bytes, bytes]:
    source = data_path / _RAW_FILE_NAME
    assert raw_win._load_file(image_or_label_path=str(source))
    replacement = tmp_path / "replacement.jpg"
    shutil.copy(source, replacement)
    original_image = tmp_path / "original.jpg"
    shutil.copy(source, original_image)
    missing_image = tmp_path / "missing.jpg"
    annotation = tmp_path / "original.json"
    raw = {
        "version": "6.0.0",
        "flags": {},
        "shapes": [
            {
                "label": "recovered",
                "points": [[10.0, 10.0], [50.0, 50.0]],
                "shape_type": "rectangle",
            }
        ],
        "imagePath": str(missing_image) if absolute else missing_image.name,
        "imageData": None,
        "imageHeight": 338,
        "imageWidth": 500,
    }
    annotation.write_text(json.dumps(raw), encoding="utf-8")
    existing_annotation = replacement.with_suffix(".json")
    existing_annotation.write_text(
        json.dumps({**raw, "imagePath": replacement.name, "flags": {"keep": True}}),
        encoding="utf-8",
    )
    original_bytes = annotation.read_bytes()
    replacement_bytes = existing_annotation.read_bytes()
    raw_win._actions.save_auto.setChecked(True)
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(replacement), ""),
    )

    def locate_image() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        next(b for b in dialog.buttons() if "Locate Image" in b.text()).click()

    QTimer.singleShot(0, locate_image)
    assert raw_win._load_file(
        image_or_label_path=str(original_image if open_via_image else annotation)
    )
    return annotation, existing_annotation, original_bytes, replacement_bytes


@pytest.mark.gui
@pytest.mark.parametrize("absolute", [False, True], ids=["relative", "absolute"])
@pytest.mark.parametrize("save_as", [False, True], ids=["save", "save-as"])
@pytest.mark.parametrize("open_via_image", [False, True], ids=["annotation", "image"])
def test_recovery_waits_for_explicit_save_and_keeps_destination(
    *,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    pause: bool,
    absolute: bool,
    save_as: bool,
    open_via_image: bool,
) -> None:
    annotation, existing_annotation, original_bytes, replacement_bytes = (
        _recover_annotation(
            raw_win=raw_win,
            data_path=data_path,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            absolute=absolute,
            open_via_image=open_via_image,
        )
    )
    shape = raw_win._canvas_widgets.canvas.shapes[0]
    shape.label = "edited before confirmation"
    raw_win.mark_dirty()
    raw_win._actions.save_auto.setChecked(False)
    raw_win._actions.save_auto.setChecked(True)
    raw_win.mark_dirty()
    qtbot.wait(50)
    assert not raw_win._save_writer.is_busy
    assert raw_win._is_changed
    assert annotation.read_bytes() == original_bytes
    assert existing_annotation.read_bytes() == replacement_bytes

    destination = tmp_path / "saved-as.json" if save_as else annotation
    if save_as:
        monkeypatch.setattr(raw_win, "prompt_save_file_path", lambda: "")
        raw_win._save_label_file(save_as=True)
        assert raw_win._is_changed
        assert annotation.read_bytes() == original_bytes
        assert existing_annotation.read_bytes() == replacement_bytes
        monkeypatch.setattr(raw_win, "prompt_save_file_path", lambda: str(destination))
    raw_win._save_label_file(save_as=save_as)
    assert not raw_win._is_changed
    saved = json.loads(destination.read_text(encoding="utf-8"))
    assert saved["imagePath"] == "replacement.jpg"
    assert saved["shapes"][0]["label"] == "edited before confirmation"

    shape.label = "edited after confirmation"
    raw_win.mark_dirty()
    qtbot.waitUntil(lambda: not raw_win._is_changed, timeout=5_000)
    assert (
        json.loads(destination.read_text(encoding="utf-8"))["shapes"][0]["label"]
        == "edited after confirmation"
    )
    assert existing_annotation.read_bytes() == replacement_bytes
    if save_as:
        assert annotation.read_bytes() == original_bytes
    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("action", ["Save", "Discard", "Cancel"])
@pytest.mark.parametrize("transition", ["navigate", "close"])
def test_recovery_uses_unsaved_changes_decision(
    *,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    pause: bool,
    action: str,
    transition: str,
) -> None:
    annotation, existing_annotation, original_bytes, replacement_bytes = (
        _recover_annotation(
            raw_win=raw_win,
            data_path=data_path,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            absolute=False,
            open_via_image=False,
        )
    )
    recovered_annotation = raw_win._annotation
    choices: list[str] = []

    def choose(
        *_args: object, **_kwargs: object
    ) -> QtWidgets.QMessageBox.StandardButton:
        choices.append(action)
        return getattr(QtWidgets.QMessageBox.StandardButton, action)

    monkeypatch.setattr(QtWidgets.QMessageBox, "question", choose)
    if transition == "close":
        continued = raw_win.close()
    else:
        # Use the Image List's navigation entry point, which owns the decision.
        item = QtWidgets.QListWidgetItem(str(data_path / _RAW_FILE_NAME))
        item.setData(Qt.ItemDataRole.UserRole, str(data_path / _RAW_FILE_NAME))
        continued = raw_win._load_selected_image(item, None)
    assert continued is (action != "Cancel")
    assert choices == [action]
    assert existing_annotation.read_bytes() == replacement_bytes
    if action == "Save":
        assert json.loads(annotation.read_text(encoding="utf-8"))["imagePath"] == (
            "replacement.jpg"
        )
    else:
        assert annotation.read_bytes() == original_bytes
    if action == "Cancel":
        assert raw_win._annotation is recovered_annotation
        assert raw_win._is_changed
    if transition == "navigate" and continued:
        assert not raw_win._requires_explicit_save
    raw_win.mark_clean()
    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_recovery_rejects_oversized_replacement_before_decoding(
    *,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    critical_messages: list[str],
    pause: bool,
) -> None:
    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    oversized_image = tmp_path / "oversized.png"
    oversized_image.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", struct.pack(">IIBBBBB", 37296, 49319, 8, 2, 0, 0, 0))
        + make_chunk(b"IDAT", b"")
        + make_chunk(b"IEND", b"")
    )
    assert raw_win._load_file(image_or_label_path=str(data_path / _RAW_FILE_NAME))
    previous_annotation = raw_win._annotation
    annotation = tmp_path / "missing.json"
    annotation.write_text(
        json.dumps({"imagePath": "missing.jpg", "imageData": None, "shapes": []}),
        encoding="utf-8",
    )
    original_bytes = annotation.read_bytes()
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(oversized_image), ""),
    )

    def locate_image() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        next(b for b in dialog.buttons() if "Locate Image" in b.text()).click()

    QTimer.singleShot(0, locate_image)
    assert not raw_win._load_file(image_or_label_path=str(annotation))
    assert len(critical_messages) == 1
    assert "37296x49319" in critical_messages[0]
    assert "32767" in critical_messages[0]
    assert raw_win._annotation is previous_annotation
    assert annotation.read_bytes() == original_bytes
    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_recovery_failed_save_keeps_auto_save_paused_until_retry(
    *,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    pause: bool,
) -> None:
    annotation, existing_annotation, original_bytes, replacement_bytes = (
        _recover_annotation(
            raw_win=raw_win,
            data_path=data_path,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            absolute=False,
            open_via_image=False,
        )
    )

    def fail_save(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk unavailable")

    with monkeypatch.context() as patch:
        patch.setattr("labelme._app.write_save_request", fail_save)
        assert not raw_win.save_labels(label_path=str(annotation), show_error=False)
    raw_win._canvas_widgets.canvas.shapes[0].label = "edited after failure"
    raw_win.mark_dirty()
    qtbot.wait(50)
    assert not raw_win._save_writer.is_busy
    assert raw_win._is_changed
    assert annotation.read_bytes() == original_bytes
    assert existing_annotation.read_bytes() == replacement_bytes

    raw_win._retry_save()
    qtbot.waitUntil(lambda: not raw_win._is_changed, timeout=5_000)
    assert not raw_win._requires_explicit_save
    saved = json.loads(annotation.read_text(encoding="utf-8"))
    assert saved["imagePath"] == "replacement.jpg"
    assert saved["shapes"][0]["label"] == "edited after failure"
    assert existing_annotation.read_bytes() == replacement_bytes
    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)
