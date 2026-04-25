from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from labelme.widgets.file_dialog_preview import FileDialogPreview

from ...conftest import close_or_pause


@pytest.fixture()
def _file_preview_widget(qtbot: QtBot) -> FileDialogPreview:
    widget = FileDialogPreview()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


@pytest.mark.gui
def test_on_change_valid_json(
    _file_preview_widget: FileDialogPreview,
    tmp_path: Path,
    qtbot: QtBot,
    pause: bool,
) -> None:
    path = tmp_path / "valid.json"
    path.write_text(json.dumps({"version": "5.0.0", "shapes": []}))

    _file_preview_widget._on_change(str(path))

    assert _file_preview_widget.label_preview.isHidden() is False
    assert '"version"' in _file_preview_widget.label_preview.label.text()

    close_or_pause(qtbot=qtbot, widget=_file_preview_widget, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    "content_bytes",
    [
        b"not valid json {{{{",
        bytes(range(256)),
    ],
    ids=["malformed_json", "binary_file"],
)
def test_on_change_bad_json_no_crash(
    _file_preview_widget: FileDialogPreview,
    tmp_path: Path,
    content_bytes: bytes,
    qtbot: QtBot,
    pause: bool,
) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(content_bytes)

    _file_preview_widget._on_change(str(path))

    assert _file_preview_widget.label_preview.isHidden() is False
    assert "Cannot preview" in _file_preview_widget.label_preview.label.text()

    close_or_pause(qtbot=qtbot, widget=_file_preview_widget, pause=pause)


@pytest.mark.gui
def test_on_change_non_json_non_image_hides_preview(
    _file_preview_widget: FileDialogPreview,
) -> None:
    _file_preview_widget._on_change("/nonexistent/path.txt")

    assert _file_preview_widget.label_preview.isHidden() is True
