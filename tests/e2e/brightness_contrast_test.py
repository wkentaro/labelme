from __future__ import annotations

from pathlib import Path

import numpy as np
import PIL.Image
from PySide6 import QtCore
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF
from pytestqt.qtbot import QtBot

from labelme import _image_codec
from labelme._app import MainWindow
from labelme._widgets._brightness_contrast_dialog import BrightnessContrastDialog

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import canvas_pixels
from .conftest import save_12bit_ramp
from .conftest import show_window_and_wait_for_imagedata


def _brighten_then_restore_defaults(*, win: MainWindow) -> None:
    def act() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        if not isinstance(dialog, BrightnessContrastDialog):
            QtCore.QTimer.singleShot(50, win, act)
            return
        dialog.slider_brightness.setValue(150)
        buttons = dialog.findChild(QtWidgets.QDialogButtonBox)
        assert buttons is not None
        restore = buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults
        )
        assert restore is not None
        restore.click()
        dialog.close()

    QtCore.QTimer.singleShot(0, win, act)
    win._actions.brightness_contrast.trigger()


def test_brightness_contrast_dialog(
    *,
    annotated_win: MainWindow,
    qtbot: QtBot,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    original_pixmap = canvas.pixmap.copy()
    canvas.pan_view(step=QPointF(17, 23), constrain_to_center=False)
    expected_view_offset = canvas.get_view_offset()

    assert annotated_win._annotation is not None
    dialog = BrightnessContrastDialog(
        img=_image_codec.img_data_to_pil(img_data=annotated_win._annotation.image_data),
        callback=annotated_win._on_brightness_contrast_changed,
        parent=annotated_win,
    )
    qtbot.addWidget(dialog)

    dialog.slider_brightness.setValue(150)
    dialog.slider_contrast.setValue(50)
    dialog.apply()

    updated_pixmap = canvas.pixmap
    assert original_pixmap.toImage() != updated_pixmap.toImage()
    assert canvas.get_view_offset() == expected_view_offset

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


def test_kept_brightness_contrast_leaves_no_dialog_per_image(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw"),
        config_overrides={"keep_prev_brightness_contrast": True},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    image_path = win._image_path
    assert image_path is not None
    win._brightness_contrast_values[image_path] = (150, 100)

    for _ in range(2):
        previous_path = win._image_path
        win._open_next_image()
        qtbot.waitUntil(
            lambda previous_path=previous_path: win._image_path != previous_path
        )

    assert win.findChildren(BrightnessContrastDialog) == []

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_restore_defaults_shows_a_16bit_image_as_it_opened(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    image_path = tmp_path / "ramp.png"
    save_12bit_ramp(path=image_path)
    win = main_win(file_or_dir=image_path)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    opened = canvas_pixels(win=win)

    _brighten_then_restore_defaults(win=win)

    np.testing.assert_array_equal(canvas_pixels(win=win), opened)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_kept_neutral_brightness_contrast_shows_the_next_16bit_image_as_is(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    for name in ("a.png", "b.png"):
        save_12bit_ramp(path=tmp_path / name)
    win = main_win(
        file_or_dir=tmp_path,
        config_overrides={"keep_prev_brightness_contrast": True},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    opened = canvas_pixels(win=win)
    _brighten_then_restore_defaults(win=win)

    win._open_next_image()
    qtbot.waitUntil(lambda: win._image_path == str(tmp_path / "b.png"))

    np.testing.assert_array_equal(canvas_pixels(win=win), opened)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
