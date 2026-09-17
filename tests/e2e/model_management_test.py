from __future__ import annotations

import gc
import hashlib
import shutil
import threading
import weakref
from pathlib import Path
from typing import ClassVar

import osam
import pytest
from osam.types import GenerateRequest
from osam.types import GenerateResponse
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._widgets._models_widget import ModelsWidget
from labelme._yaml import safe_load

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import show_window_and_wait_for_imagedata


class _LocalSam3(osam.types.Model):
    name = "sam3:latest"
    metadata = osam.apis.get_model_metadata(name)
    _blobs: ClassVar[dict[str, osam.types.Blob]] = {}

    def generate(self, request: GenerateRequest) -> GenerateResponse:  # noqa: GR005 -- upstream API
        assert self._inference_sessions["model"].get_providers()
        return GenerateResponse(model=request.model, annotations=[])


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
    canvas = win._canvas_widgets.canvas
    canvas.load_shapes(shapes=[Shape(label="cat")])
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
    assert [shape.label for shape in canvas.shapes] == ["cat"]
    win.close()
    reopened = main_win(config_file=config)
    assert reopened._ai_text.get_model_name() == ""
    assert reopened._ai_annotation.current_model_id == ""
    assert requests == ["/slow"]


@pytest.mark.gui
def test_delete_releases_loaded_assist_and_text_sessions(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    data_path: Path,
    session_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(session_home))
    monkeypatch.setenv("USERPROFILE", str(session_home))
    artifact = Path(osam.apis.__file__).parent / "_data/non_maximum_suppression.onnx"
    content = artifact.read_bytes()
    blob = osam.types.Blob(
        url="https://example.invalid/local.onnx",
        hash="sha256:" + hashlib.sha256(content).hexdigest(),
    )
    Path(blob.path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(artifact, blob.path)
    monkeypatch.setattr(_LocalSam3, "_blobs", {"model": blob})
    monkeypatch.setattr(
        osam.apis,
        "registered_model_types",
        [
            _LocalSam3 if model.name == _LocalSam3.name else model
            for model in osam.apis.registered_model_types
        ],
    )
    config = tmp_path / "config.yaml"
    config.write_text("ai:\n  default: Sam3\n  text_model: sam3:latest\n")
    win = main_win(file_or_dir=data_path / "raw/2011_000003.jpg", config_file=config)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    canvas.load_shapes(shapes=[Shape(label="cat")])

    win._switch_canvas_mode(edit=False, create_mode="ai_box_to_shape")
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=(0.25, 0.25))
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=(0.75, 0.75))
    win._switch_canvas_mode(edit=False, create_mode="rectangle")
    win._ai_text._text_input.setText("cat")
    run = next(
        button
        for button in win._ai_text.findChildren(QtWidgets.QToolButton)
        if button.text() == "Run"
    )
    run.click()

    assist_session = canvas._ai_assist_session._session
    text_session = win._text_osam_session
    assert assist_session is not None and assist_session._model is not None
    assert text_session is not None and text_session._model is not None
    assist_model = weakref.ref(assist_session._model)
    text_model = weakref.ref(text_session._model)
    del assist_session, text_session

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_args: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    win._open_models()
    dialog = win._settings_dialog
    assert dialog is not None
    models = dialog.findChild(ModelsWidget)
    assert models is not None
    models._rows[_LocalSam3.name][2].click()
    gc.collect()

    assert assist_model() is None
    assert text_model() is None
    assert not Path(blob.path).exists()
    assert win._ai_text.get_model_name() == ""
    assert canvas.get_ai_model_name() == ""
    assert [shape.label for shape in canvas.shapes] == ["cat"]
    win.close()
    reopened = main_win(config_file=config)
    assert reopened._ai_text.get_model_name() == ""
    assert reopened._ai_annotation.current_model_id == ""
    assert not Path(blob.path).exists()


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
    # Large platform fonts can already require scrolling on the offscreen display.
    QtWidgets.QApplication.processEvents()
    initial_scroll_maximum = dialog._page._scroll_area.horizontalScrollBar().maximum()
    download.click()
    qtbot.waitUntil(
        lambda: win._model_manager.get_state(name) == "failed", timeout=20_000
    )
    assert status.text() == "Failed"
    assert download.text() == "Retry"
    assert download.accessibleName() == "Retry EfficientSam (speed)"
    QtWidgets.QApplication.processEvents()
    assert (
        dialog._page._scroll_area.horizontalScrollBar().maximum()
        == initial_scroll_maximum
    )
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
    # Subpixel antialiasing adds colored fringes even to neutral text on Linux.
    font = link.font()
    font.setStyleStrategy(QtGui.QFont.StyleStrategy.NoSubpixelAntialias)
    link.setFont(font)
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
