from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import osam
import pytest
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets._models_widget import ModelsWidget
from labelme._yaml import safe_load

from .conftest import MainWinFactory


@pytest.mark.gui
def test_download_does_not_select_and_delete_clears_both_sam3_choices(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, requests, release = download_server
    name = "sam3:latest"
    blob = osam.types.Blob(
        url=origin + "/slow", hash="sha256:" + hashlib.sha256(b"weights").hexdigest()
    )
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name), "_blobs", {"model": blob}
    )
    config = tmp_path / "config.yaml"
    config.write_text("ai:\n  default: Sam3\n  text_model: sam3:latest\n")
    win = main_win(config_file=config)
    assist = win._ai_annotation._model_combo
    text = win._ai_text._model_combo
    for picker in (assist, text):
        assert picker.currentIndex() == -1
        assert picker.count() == 1
        assert "Unavailable" in picker.placeholderText()
    assert not requests
    assert win._config["ai"]["text_model"] == name

    text.setCurrentIndex(text.findData("manage"))
    dialog = win._settings_dialog
    assert dialog is not None
    models = dialog.findChild(ModelsWidget)
    assert models is not None
    models._rows[name][1].click()
    qtbot.waitUntil(lambda: requests == ["/slow"])
    dialog.close()
    assert win._model_manager.active == name
    release.set()
    qtbot.waitUntil(lambda: win._model_manager.get_state(name) == "downloaded")
    # The remembered choice is restored without running inference.
    assert assist.currentData() == text.currentData() == name
    assert win._text_osam_session is None
    assert win._canvas_widgets.canvas.get_ai_model_name() == name
    assert win._ai_text.get_model_name() == name

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_args: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    win._open_models()
    models._rows[name][2].click()
    assert not Path(blob.path).exists()
    assert win._ai_text.get_model_name() == ""
    assert win._canvas_widgets.canvas.get_ai_model_name() == ""
    assert safe_load(config.read_text())["ai"] == {"default": None, "text_model": None}
    assert not win._canvas_widgets.canvas.shapes
    win.close()
    reopened = main_win(config_file=config)
    assert reopened._ai_text.get_model_name() == ""
    assert reopened._ai_annotation.current_model_id == ""
    assert requests == ["/slow"]
