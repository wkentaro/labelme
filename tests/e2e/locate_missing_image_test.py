from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

import PIL.Image
import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause


def _write_annotation_with_missing_image(
    *,
    path: Path,
    points: tuple[tuple[float, float], ...] = ((10.0, 10.0), (50.0, 50.0)),
    size: tuple[int, int] = (500, 338),
) -> bytes:
    path.write_text(
        json.dumps(
            {
                "version": "6.0.0",
                "flags": {},
                "shapes": [
                    {"label": "box", "points": points, "shape_type": "rectangle"}
                ],
                "imagePath": "absent.jpg",
                "imageData": None,
                "imageHeight": size[1],
                "imageWidth": size[0],
                "reviewer": "kept",
            }
        ),
        encoding="utf-8",
    )
    return path.read_bytes()


def _answer_dialog_and_file_chooser(
    *, monkeypatch: pytest.MonkeyPatch, locate: bool, chosen_path: str
) -> None:
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (chosen_path, ""),
    )

    def answer() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        if locate:
            next(b for b in dialog.buttons() if "Locate Image" in b.text()).click()
        else:
            dialog.button(QtWidgets.QMessageBox.StandardButton.Cancel).click()

    QTimer.singleShot(0, answer)


@pytest.mark.parametrize("auto_save", [False, True], ids=["manual", "auto-save"])
@pytest.mark.parametrize("subfolder", ["", "moved"], ids=["beside", "subfolder"])
def test_locating_image_repairs_reference_and_opens_clean(
    *,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    auto_save: bool,
    subfolder: str,
) -> None:
    located_image = tmp_path / subfolder / "located.jpg"
    located_image.parent.mkdir(exist_ok=True)
    shutil.copy(data_path / "raw" / "2011_000003.jpg", located_image)
    annotation = tmp_path / "annotation.json"
    _write_annotation_with_missing_image(path=annotation)
    raw_win._actions.save_auto.setChecked(auto_save)

    _answer_dialog_and_file_chooser(
        monkeypatch=monkeypatch, locate=True, chosen_path=str(located_image)
    )
    assert raw_win._load_file(image_or_label_path=str(annotation))

    assert not raw_win._is_changed
    assert raw_win._label_file_path == str(annotation)
    assert Path(raw_win._image_path or "").samefile(located_image)
    assert [s.label for s in raw_win._canvas_widgets.canvas.shapes] == ["box"]
    saved = json.loads(annotation.read_text(encoding="utf-8"))
    assert saved["imagePath"] == str(Path(subfolder) / "located.jpg")
    # Only the reference is repaired; a full save would rewrite the version.
    assert saved["version"] == "6.0.0"
    assert saved["reviewer"] == "kept"
    assert not located_image.with_suffix(".json").exists()

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.parametrize("locate", [False, True], ids=["dialog", "file-chooser"])
def test_cancelling_locate_keeps_session_and_annotation_file(
    *,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    raw_win: MainWindow,
    tmp_path: Path,
    pause: bool,
    locate: bool,
) -> None:
    annotation = tmp_path / "annotation.json"
    original_bytes = _write_annotation_with_missing_image(path=annotation)
    session_before = raw_win._annotation

    _answer_dialog_and_file_chooser(
        monkeypatch=monkeypatch, locate=locate, chosen_path=""
    )
    assert not raw_win._load_file(image_or_label_path=str(annotation))

    assert raw_win._annotation is session_before
    assert annotation.read_bytes() == original_bytes

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


def test_locating_image_of_another_size_is_refused(
    *,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    raw_win: MainWindow,
    tmp_path: Path,
    critical_messages: list[str],
    pause: bool,
) -> None:
    other_size_image = tmp_path / "other_size.png"
    PIL.Image.new("RGB", (20, 10)).save(other_size_image)
    annotation = tmp_path / "annotation.json"
    original_bytes = _write_annotation_with_missing_image(path=annotation)
    session_before = raw_win._annotation

    _answer_dialog_and_file_chooser(
        monkeypatch=monkeypatch, locate=True, chosen_path=str(other_size_image)
    )
    assert not raw_win._load_file(image_or_label_path=str(annotation))

    assert raw_win._annotation is session_before
    assert annotation.read_bytes() == original_bytes
    assert "imageHeight mismatch" in critical_messages[0]

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


def test_failed_repair_write_reports_the_annotation_file(
    *,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    critical_messages: list[str],
    pause: bool,
) -> None:
    located_image = tmp_path / "located.jpg"
    shutil.copy(data_path / "raw" / "2011_000003.jpg", located_image)
    annotation = tmp_path / "annotation.json"
    original_bytes = _write_annotation_with_missing_image(path=annotation)
    session_before = raw_win._annotation

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("read-only folder")

    monkeypatch.setattr(os, "replace", fail_replace)
    _answer_dialog_and_file_chooser(
        monkeypatch=monkeypatch, locate=True, chosen_path=str(located_image)
    )
    assert not raw_win._load_file(image_or_label_path=str(annotation))

    assert raw_win._annotation is session_before
    assert annotation.read_bytes() == original_bytes
    assert str(annotation) in critical_messages[0]
    assert "read-only folder" in critical_messages[0]

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


def test_located_image_is_not_written_when_annotation_is_invalid(
    *,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    critical_messages: list[str],
    pause: bool,
) -> None:
    located_image = tmp_path / "located.jpg"
    shutil.copy(data_path / "raw" / "2011_000003.jpg", located_image)
    annotation = tmp_path / "annotation.json"
    original_bytes = _write_annotation_with_missing_image(
        path=annotation, points=((10.0, 10.0),)
    )
    session_before = raw_win._annotation

    _answer_dialog_and_file_chooser(
        monkeypatch=monkeypatch, locate=True, chosen_path=str(located_image)
    )
    assert not raw_win._load_file(image_or_label_path=str(annotation))

    assert raw_win._annotation is session_before
    assert annotation.read_bytes() == original_bytes
    assert "shapes[0]" in critical_messages[0]

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


def test_located_image_is_not_written_when_large_image_is_declined(
    *,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    raw_win: MainWindow,
    tmp_path: Path,
    set_allocation_limit: Callable[[int], None],
    pause: bool,
) -> None:
    size = (800, 600)
    located_image = tmp_path / "located.png"
    PIL.Image.new("RGB", size).save(located_image)
    annotation = tmp_path / "annotation.json"
    original_bytes = _write_annotation_with_missing_image(path=annotation, size=size)
    session_before = raw_win._annotation
    declined: list[object] = []

    def decline(**kwargs: object) -> bool:
        declined.append(kwargs["limit_mb"])
        return False

    set_allocation_limit(1)
    monkeypatch.setattr(raw_win, "_confirm_large_image_open", decline)
    _answer_dialog_and_file_chooser(
        monkeypatch=monkeypatch, locate=True, chosen_path=str(located_image)
    )
    assert not raw_win._load_file(image_or_label_path=str(annotation))

    assert declined == [1]
    assert raw_win._annotation is session_before
    assert annotation.read_bytes() == original_bytes

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)
