from __future__ import annotations

from pathlib import Path

import PIL.features
import PIL.Image
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._label_file import read_label_file

from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import show_window_and_wait_for_imagedata
from .drag_and_drop_test import _drag_enter_accepted
from .drag_and_drop_test import _make_drop_mime
from .drag_and_drop_test import _send_drop

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        not PIL.features.check_codec("jpg_2000"), reason="Pillow needs OpenJPEG"
    ),
]


@pytest.mark.parametrize("suffix", [".jp2", ".jpx", ".j2k", ".j2c"])
@pytest.mark.parametrize("entry", ["file", "folder", "dialog", "drop"])
def test_open_jpeg2000_without_qt_decoder(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    entry: str,
) -> None:
    image_path = tmp_path / f"image{suffix.upper()}"
    PIL.Image.new("RGB", (32, 24), (34, 123, 210)).save(
        image_path, format="JPEG2000", no_jp2=suffix in (".j2k", ".j2c")
    )
    monkeypatch.setattr(
        QtGui.QImageReader,
        "supportedImageFormats",
        lambda: [QtCore.QByteArray(b"png")],
    )

    if entry in ("file", "folder"):
        win = main_win(file_or_dir=image_path if entry == "file" else tmp_path)
    else:
        win = main_win()
        win.show()
        qtbot.waitUntil(win.isVisible)
        if entry == "dialog":

            def select_file(
                _parent: QtWidgets.QWidget,
                _caption: str,
                _directory: str,
                filters: str,
                /,
            ) -> tuple[str, str]:
                for extension in ("jp2", "jpx", "j2k", "j2c"):
                    assert f"*.{extension}" in filters
                assert "*.png" in filters
                assert "*.json" in filters
                return str(image_path), ""

            monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", select_file)
            win._open_file_with_dialog()
        else:
            mime = _make_drop_mime(paths=[image_path])
            assert _drag_enter_accepted(win=win, mime=mime)
            _send_drop(win=win, mime=mime)

    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert win._image_path == str(image_path)
    assert win.image_list == [str(image_path)]
    assert win._image.size() == QtCore.QSize(32, 24)
    assert win._image.pixelColor(0, 0) == QtGui.QColor(34, 123, 210)


@pytest.mark.parametrize("with_image_data", [True, False])
@pytest.mark.parametrize("mode", ["RGB", "I;16"])
def test_jpeg2000_annotation_round_trip(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    with_image_data: bool,
    mode: str,
) -> None:
    image_path = tmp_path / "image.jp2"
    image = (
        PIL.Image.new("I;16", (64, 48), 32768)
        if mode == "I;16"
        else PIL.Image.new("RGB", (64, 48), (34, 123, 210))
    )
    image.save(image_path, format="JPEG2000")
    source_bytes = image_path.read_bytes()
    win = main_win(
        file_or_dir=image_path, config_overrides={"with_image_data": with_image_data}
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    draw_and_commit_polygon(
        qtbot=qtbot,
        win=win,
        label="object",
        vertices=((0.2, 0.2), (0.8, 0.2), (0.5, 0.8)),
    )
    win._save_label_file(save_as=False)
    win._wait_for_save()
    annotation_path = image_path.with_suffix(".json")
    annotation = read_label_file(filename=str(annotation_path))
    assert annotation.image_path == image_path.name
    assert len(annotation.shapes) == 1
    assert annotation.shapes[0]["label"] == "object"

    reopened = main_win(file_or_dir=annotation_path)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=reopened)
    expected_color = (
        QtGui.QColor.fromRgba64(32768, 32768, 32768, 65535)
        if mode == "I;16"
        else QtGui.QColor(34, 123, 210)
    )
    assert reopened._image.pixelColor(0, 0) == expected_color
    assert len(reopened._canvas_widgets.canvas.shapes) == 1
    assert reopened._canvas_widgets.canvas.shapes[0].label == "object"
    assert image_path.read_bytes() == source_bytes
