from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import osam
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
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
    for key in ("default", "text_model"):
        editor = dialog._editors[("ai", key)]
        assert isinstance(editor, QtWidgets.QComboBox)
        assert editor.currentData() is None
        assert editor.currentText() == "(none)"
    assert win._ai_text.get_model_name() == ""
    assert win._canvas_widgets.canvas.get_ai_model_name() == ""
    assert safe_load(config.read_text())["ai"] == {"default": None, "text_model": None}
    assert not win._canvas_widgets.canvas.shapes
    win.close()
    reopened = main_win(config_file=config)
    assert reopened._ai_text.get_model_name() == ""
    assert reopened._ai_annotation.current_model_id == ""
    assert requests == ["/slow"]


@pytest.mark.gui
@pytest.mark.parametrize("query", ["download", "AI Models", "SAM3"])
def test_find_models_and_tab_into_visible_controls(
    *, main_win: MainWinFactory, qtbot: QtBot, query: str
) -> None:
    win = main_win()
    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None
    page = dialog._page
    qtbot.waitUntil(dialog.isActiveWindow)
    qtbot.keyClicks(page._search, query)
    matches = page._navigation.findItems("AI Models", QtCore.Qt.MatchFlag.MatchExactly)
    assert len(matches) == 1
    page._navigation.setCurrentItem(matches[0])
    qtbot.keyClick(page._search, QtCore.Qt.Key.Key_Return)
    qtbot.keyClick(page._navigation, QtCore.Qt.Key.Key_Tab)
    models = dialog.findChild(ModelsWidget)
    assert models is not None
    focused = dialog.focusWidget()
    assert focused is not None and models.isAncestorOf(focused)
    viewport = page._scroll_area.viewport()
    assert viewport.rect().contains(focused.mapTo(viewport, focused.rect().center()))


@pytest.mark.gui
def test_failed_download_keeps_retry_visible_and_details_accessible(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, _, _ = download_server
    name = "efficientsam:10m"
    blob = osam.types.Blob(
        url=origin + "/bad", hash="sha256:" + hashlib.sha256(b"weights").hexdigest()
    )
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name), "_blobs", {"model": blob}
    )
    win = main_win()
    win._open_models()
    dialog = win._settings_dialog
    assert dialog is not None
    models = dialog.findChild(ModelsWidget)
    assert models is not None
    status, download, _, details = models._rows[name]
    download.click()
    qtbot.waitUntil(
        lambda: win._model_manager.get_state(name) == "failed", timeout=20_000
    )
    assert status.text() == "Failed"
    assert download.text() == "Retry"
    assert download.accessibleName() == "Retry EfficientSam (speed)"
    assert dialog._page._scroll_area.horizontalScrollBar().maximum() == 0
    assert details.isVisible()

    messages = []

    def inspect_details(message: QtWidgets.QMessageBox) -> int:
        messages.append(message.detailedText())
        return 0

    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", inspect_details)
    details.click()
    assert messages == [win._model_manager.errors[name]]
    download.click()
    assert download.text() == "Cancel"
    assert not details.isVisible()
    download.click()
    qtbot.waitUntil(lambda: win._model_manager._pull is None)


@pytest.mark.gui
def test_model_links_follow_live_theme_contrast(
    *, main_win: MainWinFactory, qtbot: QtBot
) -> None:
    win = main_win()
    win._open_models()
    dialog = win._settings_dialog
    assert dialog is not None
    models = dialog.findChild(ModelsWidget)
    assert models is not None
    link = next(
        label
        for label in models.findChildren(QtWidgets.QLabel)
        if label.openExternalLinks()
    )
    qtbot.waitUntil(dialog.isActiveWindow)
    for foreground, background in (("white", "black"), ("black", "white")):
        palette = dialog.palette()
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(foreground))
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(background))
        dialog.setPalette(palette)
        image = link.grab().toImage()
        for x in range(image.width()):
            for y in range(image.height()):
                color = image.pixelColor(x, y)
                assert color.red() == color.green() == color.blue()
        assert (
            link.textInteractionFlags()
            & QtCore.Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
