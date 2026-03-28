from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from labelme.widgets.file_dialog_preview import FileDialogPreview


@pytest.fixture()
def _file_preview_widget(qtbot: QtBot) -> FileDialogPreview:
    widget = FileDialogPreview()
    qtbot.addWidget(widget)
    return widget


def _show_and_wait(widget: FileDialogPreview, qtbot: QtBot) -> None:
    widget.show()
    qtbot.waitExposed(widget)
    qtbot.waitUntil(lambda: not widget.isVisible(), timeout=30_000)


@pytest.mark.gui
def test_onChange_valid_json(
    _file_preview_widget: FileDialogPreview,
    tmp_path: Path,
    qtbot: QtBot,
    show: bool,
) -> None:
    path = tmp_path / "valid.json"
    path.write_text(json.dumps({"version": "5.0.0", "shapes": []}))

    _file_preview_widget.onChange(str(path))

    assert _file_preview_widget.labelPreview.isHidden() is False
    assert '"version"' in _file_preview_widget.labelPreview.label.text()

    if show:
        _show_and_wait(_file_preview_widget, qtbot)


@pytest.mark.gui
@pytest.mark.parametrize(
    "content_bytes",
    [
        b"not valid json {{{{",
        bytes(range(256)),
    ],
    ids=["malformed_json", "binary_file"],
)
def test_onChange_bad_json_no_crash(
    _file_preview_widget: FileDialogPreview,
    tmp_path: Path,
    content_bytes: bytes,
    qtbot: QtBot,
    show: bool,
) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(content_bytes)

    _file_preview_widget.onChange(str(path))

    assert _file_preview_widget.labelPreview.isHidden() is False
    assert "Cannot preview" in _file_preview_widget.labelPreview.label.text()

    if show:
        _show_and_wait(_file_preview_widget, qtbot)


@pytest.mark.gui
def test_onChange_non_json_non_image_hides_preview(
    _file_preview_widget: FileDialogPreview,
) -> None:
    _file_preview_widget.onChange("/nonexistent/path.txt")

    assert _file_preview_widget.labelPreview.isHidden() is True
