from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme._utils import apply_color_theme


@pytest.fixture(autouse=True)
def restore_palette(*, qapp: QtWidgets.QApplication) -> Iterator[None]:
    original = qapp.palette()
    yield
    qapp.setPalette(original)


@pytest.fixture()
def unsupported_scheme(*, monkeypatch: pytest.MonkeyPatch) -> None:
    hints = QtGui.QGuiApplication.styleHints()
    monkeypatch.setattr(hints, "setColorScheme", lambda _scheme: None)
    monkeypatch.setattr(hints, "colorScheme", lambda: QtCore.Qt.ColorScheme.Unknown)


@pytest.mark.usefixtures("unsupported_scheme")
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_explicit_theme_sets_a_readable_palette_when_platform_ignores_it(
    *, qapp: QtWidgets.QApplication, theme: str
) -> None:
    apply_color_theme(theme=theme)
    palette = qapp.palette()
    dark = theme == "dark"
    assert (palette.window().color().lightness() < 128) == dark
    assert (palette.windowText().color().lightness() > 128) == dark
    assert (palette.base().color().lightness() < 128) == dark
    assert (
        palette.color(QtGui.QPalette.ColorRole.PlaceholderText)
        != palette.text().color()
    )
    assert (
        palette.color(
            QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.WindowText
        )
        != palette.windowText().color()
    )
    if dark:
        assert palette.color(QtGui.QPalette.ColorRole.Link).lightness() > 128
        assert (
            palette.color(
                QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.WindowText
            ).lightness()
            > palette.window().color().lightness()
        )


@pytest.mark.usefixtures("unsupported_scheme")
def test_system_theme_clears_fallback_instead_of_pinning_old_platform_colors(
    *, qapp: QtWidgets.QApplication
) -> None:
    qapp.setPalette(QtGui.QPalette())
    system = qapp.palette()
    apply_color_theme(theme="dark")
    apply_color_theme(theme="light")
    apply_color_theme(theme="system")
    assert qapp.palette() == system
    assert qapp.palette().resolveMask() == 0


def test_native_theme_palette_is_preserved(
    *, qapp: QtWidgets.QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = QtGui.QPalette(QtGui.QColor("#203040"))
    native.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#ddffff"))
    hints = QtGui.QGuiApplication.styleHints()
    monkeypatch.setattr(
        hints, "setColorScheme", lambda _scheme: qapp.setPalette(native)
    )
    monkeypatch.setattr(hints, "colorScheme", lambda: QtCore.Qt.ColorScheme.Dark)
    apply_color_theme(theme="dark")
    for role in (QtGui.QPalette.ColorRole.Window, QtGui.QPalette.ColorRole.WindowText):
        assert qapp.palette().color(role) == native.color(role)
