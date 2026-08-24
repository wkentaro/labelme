from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._utils import apply_color_theme

from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_empty_state_replaced_after_image_load(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win: MainWindow = main_win()
    win.show()
    qtbot.waitExposed(win)

    empty_state = win.findChild(QtWidgets.QWidget, "emptyState")
    assert empty_state is not None
    assert empty_state.isVisible()
    assert empty_state.accessibleName() == "Start annotating"
    assert "image files" in empty_state.accessibleDescription()
    drop_hint = empty_state.findChild(QtWidgets.QLabel, "emptyStateDropHint")
    assert drop_hint is not None
    assert drop_hint.text() == "Or drag and drop image files here"

    assert win._load_file(str(data_path / "raw" / "2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    assert not empty_state.isVisible()
    assert win._canvas_widgets.canvas.isVisible()

    win.close_file()
    assert empty_state.isVisible()
    assert not win._canvas_widgets.canvas.isVisible()


@pytest.mark.gui
@pytest.mark.parametrize(
    ("button_name", "dialog_method", "dialog_result"),
    [
        pytest.param(
            "emptyStateOpenImage",
            "getOpenFileName",
            lambda data_path: (str(data_path / "raw" / "2011_000003.jpg"), ""),
            id="open_image",
        ),
        pytest.param(
            "emptyStateOpenDirectory",
            "getExistingDirectory",
            lambda data_path: str(data_path / "annotated"),
            id="open_directory",
        ),
    ],
)
def test_empty_state_actions_are_keyboard_reachable(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    button_name: str,
    dialog_method: str,
    dialog_result: Callable[[Path], tuple[str, str] | str],
) -> None:
    win: MainWindow = main_win()
    win.show()
    qtbot.waitExposed(win)
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        dialog_method,
        lambda *args, **kwargs: dialog_result(data_path),
    )

    button = win.findChild(QtWidgets.QPushButton, button_name)
    assert button is not None
    assert button.focusPolicy() & QtCore.Qt.FocusPolicy.TabFocus
    qtbot.keyClick(button, QtCore.Qt.Key.Key_Space)

    qtbot.waitUntil(lambda: win._image_path is not None)
    assert not win._canvas_widgets.empty_state.isVisible()
    assert win._canvas_widgets.canvas.isVisible()


def _calculate_relative_luminance(color: QtGui.QColor) -> float:
    channels = []
    for value in (color.redF(), color.greenF(), color.blueF()):
        channels.append(
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _calculate_contrast_ratio(
    foreground: QtGui.QColor, background: QtGui.QColor
) -> float:
    lighter, darker = sorted(
        (
            _calculate_relative_luminance(foreground),
            _calculate_relative_luminance(background),
        ),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.gui
@pytest.mark.parametrize("theme", ["system", "light", "dark"])
def test_empty_state_is_legible_in_every_theme(
    main_win: MainWinFactory,
    qtbot: QtBot,
    theme: str,
) -> None:
    try:
        win: MainWindow = main_win(config_overrides={"color_theme": theme})
        win.show()
        qtbot.waitExposed(win)
        empty_state = win._canvas_widgets.empty_state
        palette = empty_state.palette()

        assert empty_state.isVisible()
        assert (
            _calculate_contrast_ratio(
                palette.color(QtGui.QPalette.ColorRole.WindowText),
                palette.color(QtGui.QPalette.ColorRole.Base),
            )
            >= 4.5
        )
    finally:
        apply_color_theme(theme="system")
