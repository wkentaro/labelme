from __future__ import annotations

import math
import sys

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF
from pytestqt.qtbot import QtBot

from labelme._utils._qt import _TintedSvgIconEngine
from labelme._utils._qt import _toolbar_label
from labelme._utils._qt import direction_angle
from labelme._utils._qt import modifier_text
from labelme._utils._qt import new_action
from labelme._utils._qt import new_icon
from labelme._utils._qt import new_separator
from labelme._utils._qt import project_point_on_line
from labelme._utils._qt import project_point_on_perpendicular_line


@pytest.mark.parametrize(
    "end, expected",
    [
        ((5.0, 0.0), 0.0),
        ((0.0, 5.0), math.pi / 2),
        ((-5.0, 0.0), math.pi),
        ((0.0, -5.0), -math.pi / 2),
    ],
)
def test_direction_angle(*, end: tuple[float, float], expected: float) -> None:
    assert direction_angle(start=(0.0, 0.0), end=end) == pytest.approx(expected)


@pytest.mark.parametrize(
    "point, expected",
    [
        (QPointF(15.0, 7.0), (10.0, 7.0)),
        (QPointF(10.0, 7.0), (10.0, 7.0)),
        (QPointF(0.0, 7.0), (10.0, 7.0)),
    ],
)
def test_project_point_on_perpendicular_line(
    *, point: QPointF, expected: tuple[float, float]
) -> None:
    projected = project_point_on_perpendicular_line(
        point=point, line_start=QPointF(0.0, 0.0), line_end=QPointF(10.0, 0.0)
    )
    assert (projected.x(), projected.y()) == pytest.approx(expected)


def test_project_point_on_perpendicular_line_zero_length_returns_point() -> None:
    # A zero-length line has no direction, so the perpendicular is undefined and
    # the point is returned unchanged instead of dividing by the zero length.
    point = QPointF(4.0, 7.0)
    projected = project_point_on_perpendicular_line(
        point=point, line_start=QPointF(2.0, 2.0), line_end=QPointF(2.0, 2.0)
    )
    assert (projected.x(), projected.y()) == pytest.approx((4.0, 7.0))


@pytest.mark.parametrize(
    "point, expected",
    [
        (QPointF(4.0, 0.0), (4.0, 0.0)),
        (QPointF(4.0, 7.0), (4.0, 0.0)),
    ],
)
def test_project_point_on_line(
    *, point: QPointF, expected: tuple[float, float]
) -> None:
    projected = project_point_on_line(
        point=point, line_start=QPointF(0.0, 0.0), line_end=QPointF(10.0, 0.0)
    )
    assert (projected.x(), projected.y()) == pytest.approx(expected)


def test_project_point_on_line_zero_length_returns_point() -> None:
    # A zero-length line has no direction to project onto, so the point is
    # returned unchanged instead of dividing by the zero length.
    point = QPointF(4.0, 7.0)
    projected = project_point_on_line(
        point=point, line_start=QPointF(2.0, 2.0), line_end=QPointF(2.0, 2.0)
    )
    assert (projected.x(), projected.y()) == pytest.approx((4.0, 7.0))


# ---------------------------------------------------------------------------
# new_icon
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("qtbot")
def test_new_icon_returns_qicon() -> None:
    icon = new_icon("icon-256")
    assert isinstance(icon, QtGui.QIcon)
    assert not icon.isNull()


@pytest.mark.usefixtures("qtbot")
def test_new_icon_with_explicit_png_suffix() -> None:
    icon = new_icon("icon-256.png")
    assert isinstance(icon, QtGui.QIcon)
    assert not icon.isNull()


@pytest.mark.usefixtures("qtbot")
def test_new_icon_with_path_that_includes_subdir() -> None:
    icon = new_icon("phosphor/info.svg")
    assert isinstance(icon, QtGui.QIcon)
    assert not icon.isNull()


# ---------------------------------------------------------------------------
# color-theme icon tinting
# ---------------------------------------------------------------------------


def _set_window_text(app: QtWidgets.QApplication, /, *, color: QtGui.QColor) -> None:
    palette = app.palette()
    palette.setColor(
        QtGui.QPalette.ColorGroup.Normal, QtGui.QPalette.ColorRole.WindowText, color
    )
    app.setPalette(palette)


def test_tinted_svg_engine_renders_window_text_color(
    *,
    qapp: QtWidgets.QApplication,
) -> None:
    original = qapp.palette()
    try:
        _set_window_text(qapp, color=QtGui.QColor(255, 0, 0))
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">'
            b'<rect width="4" height="4" fill="currentColor"/></svg>'
        )
        engine = _TintedSvgIconEngine(svg=svg)
        pixmap = engine.pixmap(
            QtCore.QSize(4, 4), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off
        )
        assert pixmap.toImage().pixelColor(2, 2).getRgb() == (255, 0, 0, 255)
    finally:
        qapp.setPalette(original)


def test_tinted_svg_engine_renders_highlighted_text_color_when_selected(
    *,
    qapp: QtWidgets.QApplication,
) -> None:
    original = qapp.palette()
    try:
        palette = qapp.palette()
        palette.setColor(
            QtGui.QPalette.ColorGroup.Normal,
            QtGui.QPalette.ColorRole.HighlightedText,
            QtGui.QColor(0, 255, 0),
        )
        qapp.setPalette(palette)
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">'
            b'<rect width="4" height="4" fill="currentColor"/></svg>'
        )
        engine = _TintedSvgIconEngine(svg=svg)
        pixmap = engine.pixmap(
            QtCore.QSize(4, 4), QtGui.QIcon.Mode.Selected, QtGui.QIcon.State.Off
        )
        assert pixmap.toImage().pixelColor(2, 2).getRgb() == (0, 255, 0, 255)
    finally:
        qapp.setPalette(original)


def test_new_icon_tints_monochrome_icon_to_palette(
    *,
    qapp: QtWidgets.QApplication,
) -> None:
    original = qapp.palette()
    try:
        icon = new_icon("phosphor/polygon.svg")  # authored with fill="currentColor"
        _set_window_text(qapp, color=QtGui.QColor(255, 0, 0))
        red = icon.pixmap(QtCore.QSize(24, 24)).toImage()
        _set_window_text(qapp, color=QtGui.QColor(0, 0, 255))
        blue = icon.pixmap(QtCore.QSize(24, 24)).toImage()
        assert red != blue
    finally:
        qapp.setPalette(original)


def test_new_icon_keeps_accent_icon_fixed(*, qapp: QtWidgets.QApplication) -> None:
    original = qapp.palette()
    try:
        icon = new_icon("phosphor/floppy-disk.svg")  # baked accent color, not tinted
        _set_window_text(qapp, color=QtGui.QColor(255, 0, 0))
        a = icon.pixmap(QtCore.QSize(24, 24)).toImage()
        _set_window_text(qapp, color=QtGui.QColor(0, 255, 0))
        b = icon.pixmap(QtCore.QSize(24, 24)).toImage()
        assert a == b
    finally:
        qapp.setPalette(original)


# ---------------------------------------------------------------------------
# new_action
# ---------------------------------------------------------------------------


def test_new_action_returns_qaction(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="Open",
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert isinstance(action, QtGui.QAction)


def test_new_action_text(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="Save",
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert action.text() == "Save"


def test_new_action_enabled_by_default(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert action.isEnabled()


def test_new_action_disabled(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        enabled=False,
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        checked=False,
    )
    assert not action.isEnabled()


def test_new_action_not_checkable_by_default(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert not action.isCheckable()


def test_new_action_checkable(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        checkable=True,
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        enabled=True,
        checked=False,
    )
    assert action.isCheckable()


def test_new_action_not_checked_by_default(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        checkable=True,
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        enabled=True,
        checked=False,
    )
    assert not action.isChecked()


def test_new_action_checked(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        checkable=True,
        checked=True,
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        enabled=True,
    )
    assert action.isChecked()


def test_new_action_shortcut_string(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        shortcut="Ctrl+S",
        slot=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert action.shortcut().toString() == "Ctrl+S"


def test_new_action_shortcut_list(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        shortcut=["Ctrl+S", "Ctrl+W"],
        slot=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    keys = [s.toString() for s in action.shortcuts()]
    assert "Ctrl+S" in keys
    assert "Ctrl+W" in keys


def test_new_action_shortcut_tuple(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        shortcut=("Ctrl+S", "Ctrl+W"),
        slot=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    keys = [s.toString() for s in action.shortcuts()]
    assert "Ctrl+S" in keys
    assert "Ctrl+W" in keys


def test_new_action_tip(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        tip="My tip",
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert action.toolTip() == "My tip"
    assert action.statusTip() == "My tip"


def test_new_action_no_tip_by_default(*, qtbot: QtBot) -> None:
    # Qt 6 behavior: toolTip() falls back to the action text when no tip is set;
    # statusTip() returns empty string.
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        slot=None,
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert action.toolTip() == "X"
    assert action.statusTip() == ""


def test_new_action_with_icon_sets_icon_text(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    # Use an icon file that actually exists so Qt loads it as non-null.
    action = new_action(
        parent,
        text="Save File",
        icon="ai-box.svg",
        slot=None,
        shortcut=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    # multi-word labels are presented so words are not shown on a single unbroken line
    icon_text = action.iconText()
    assert icon_text != "Save File"  # must not be the original single-line text
    assert "Save" in icon_text
    assert "File" in icon_text
    assert not action.icon().isNull()


def test_new_action_slot(*, qtbot: QtBot) -> None:
    calls: list[bool] = []
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="X",
        slot=lambda: calls.append(True),
        shortcut=None,
        icon=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    action.trigger()
    assert calls == [True]


# ---------------------------------------------------------------------------
# new_separator
# ---------------------------------------------------------------------------


def test_new_separator_renders_as_menu_separator(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    menu = QtWidgets.QMenu(parent)
    menu.addActions([QtGui.QAction("Cut", parent), new_separator(parent)])
    assert [a.isSeparator() for a in menu.actions()] == [False, True]


def test_new_separator_survives_menu_clear(*, qtbot: QtBot) -> None:
    # Menus rebuilt at runtime keep their separator objects, so a separator must
    # belong to the caller rather than to the menu that clear() empties.
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    separator = new_separator(parent)
    menu = QtWidgets.QMenu(parent)
    menu.addAction(separator)
    menu.clear()
    menu.addAction(separator)
    assert [a.isSeparator() for a in menu.actions()] == [True]


@pytest.mark.parametrize(
    ("modifiers", "macos", "other"),
    [
        (QtCore.Qt.KeyboardModifier.ControlModifier, "⌘", "Ctrl"),
        (
            QtCore.Qt.KeyboardModifier.ControlModifier
            | QtCore.Qt.KeyboardModifier.ShiftModifier,
            "⇧⌘",
            "Ctrl+Shift",
        ),
        (QtCore.Qt.KeyboardModifier.AltModifier, "⌥", "Alt"),
    ],
)
def test_modifier_text_follows_platform(
    *, modifiers: QtCore.Qt.KeyboardModifier, macos: str, other: str
) -> None:
    expected = macos if sys.platform == "darwin" else other
    assert modifier_text(modifiers) == expected


def test_new_action_keeps_translated_line_break_out_of_menu(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="図形を\n編集",
        icon="phosphor/note-pencil.svg",
        slot=None,
        shortcut=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert action.text() == "図形を編集"
    assert action.iconText() == "図形を\n編集"


def test_new_action_shows_toolbar_text_on_the_toolbar(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="&Previous Image",
        toolbar_text="Previous",
        icon="phosphor/arrow-fat-left.svg",
        slot=None,
        shortcut=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert action.text() == "&Previous Image"
    assert action.iconText() == "Previous"


def test_new_action_drops_cjk_mnemonic_from_toolbar_label(*, qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(
        parent,
        text="保存(&S)",
        icon="phosphor/floppy-disk.svg",
        slot=None,
        shortcut=None,
        toolbar_text=None,
        tip=None,
        checkable=False,
        enabled=True,
        checked=False,
    )
    assert action.text() == "保存(&S)"
    assert action.iconText() == "保存"


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("&Save", "&Save"),
        ("&Open File…", "&Open\nFile"),
        ("&Brightness/Contrast…", "&Brightness\nContrast"),
        ("&Delete Annotation File", "&Delete\nAnnotation File"),
        ("Supprimer le fichier d'annotations", "Supprimer le fichier\nd'annotations"),
        ("Hình ảnh Tiếp theo(&N)", "Hình ảnh\nTiếp theo"),
        ("Độ sáng/Độ tương phản(&B)…", "Độ sáng\nĐộ tương phản"),
        ("図形を\n編集", "図形を\n編集"),
    ],
)
def test_toolbar_label_wraps_to_two_balanced_lines(*, text: str, label: str) -> None:
    assert _toolbar_label(text) == label
