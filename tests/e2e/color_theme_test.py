from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._utils import apply_color_theme

from .conftest import MainWinFactory
from .empty_state_test import _calculate_contrast_ratio


def test_theme_setting_updates_palette_icons_and_stylesheets(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hints = QtGui.QGuiApplication.styleHints()
    monkeypatch.setattr(hints, "setColorScheme", lambda _scheme: None)
    monkeypatch.setattr(hints, "colorScheme", lambda: QtCore.Qt.ColorScheme.Unknown)
    config = tmp_path / "config.yaml"
    config.write_text("{}")
    win = main_win(config_file=config)
    win.show()
    styled = QtWidgets.QLabel("Palette", win)
    styled.setStyleSheet("color: palette(window-text)")
    styled.show()
    system = win.palette()
    icons: list[QtGui.QImage] = []
    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None
    combo = dialog._editors[("color_theme",)]
    assert isinstance(combo, QtWidgets.QComboBox)
    try:
        for theme in ("light", "dark", "light", "system"):
            combo.setCurrentIndex(combo.findData(theme))
            dark = (
                system.window().color().lightness() < 128
                if theme == "system"
                else theme == "dark"
            )
            qtbot.waitUntil(
                lambda: (win.palette().window().color().lightness() < 128) == dark
            )
            qtbot.waitUntil(
                lambda: styled.palette().windowText() == win.palette().windowText()
            )
            icons.append(win._actions.open.icon().pixmap(24, 24).toImage())
            palette = win.palette()
            if theme == "system":
                assert palette.window() == system.window()
                assert palette.windowText() == system.windowText()
                assert palette.resolveMask() == 0
                continue
            for text, background in (
                (QtGui.QPalette.ColorRole.WindowText, QtGui.QPalette.ColorRole.Window),
                (QtGui.QPalette.ColorRole.Text, QtGui.QPalette.ColorRole.Base),
                (QtGui.QPalette.ColorRole.Link, QtGui.QPalette.ColorRole.Base),
            ):
                assert (
                    _calculate_contrast_ratio(
                        foreground=palette.color(text),
                        background=palette.color(background),
                    )
                    >= 4.5
                )
        assert icons[0] != icons[1]
        assert icons[0] == icons[2]
    finally:
        dialog.close()
        apply_color_theme(theme="system")
