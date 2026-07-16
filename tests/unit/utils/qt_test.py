from __future__ import annotations

import math

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF
from pytestqt.qtbot import QtBot

from labelme._utils.qt import _TintedSvgIconEngine
from labelme._utils.qt import add_actions
from labelme._utils.qt import direction_angle
from labelme._utils.qt import format_shortcut
from labelme._utils.qt import label_validator
from labelme._utils.qt import new_action
from labelme._utils.qt import new_icon
from labelme._utils.qt import project_point_on_line
from labelme._utils.qt import project_point_on_perpendicular_line


@pytest.mark.parametrize(
    "end, expected",
    [
        ((5.0, 0.0), 0.0),
        ((0.0, 5.0), math.pi / 2),
        ((-5.0, 0.0), math.pi),
        ((0.0, -5.0), -math.pi / 2),
    ],
)
def test_direction_angle(end: tuple[float, float], expected: float) -> None:
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
    point: QPointF, expected: tuple[float, float]
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
def test_project_point_on_line(point: QPointF, expected: tuple[float, float]) -> None:
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
# format_shortcut
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, modifier, key",
    [
        ("Ctrl+S", "Ctrl", "S"),
        ("Alt+F4", "Alt", "F4"),
        ("Shift+Z", "Shift", "Z"),
    ],
)
def test_format_shortcut(text: str, modifier: str, key: str) -> None:
    result = format_shortcut(text)
    assert result  # non-empty
    assert modifier in result
    assert key in result
    # result must contain some kind of separator between modifier and key
    assert "+" in result or result.index(modifier) < result.index(key)


def test_format_shortcut_raises_without_plus() -> None:
    with pytest.raises(ValueError):
        format_shortcut("CtrlS")


# ---------------------------------------------------------------------------
# label_validator
# ---------------------------------------------------------------------------


def test_label_validator_returns_validator() -> None:
    v = label_validator()
    assert isinstance(v, QtGui.QRegularExpressionValidator)


def test_label_validator_rejects_leading_space() -> None:
    v = label_validator()
    state, _, _ = v.validate(" label", 0)  # ty: ignore[not-iterable]
    assert state == QtGui.QValidator.State.Invalid


def test_label_validator_rejects_leading_tab() -> None:
    v = label_validator()
    state, _, _ = v.validate("\tlabel", 0)  # ty: ignore[not-iterable]
    assert state == QtGui.QValidator.State.Invalid


def test_label_validator_accepts_normal_label() -> None:
    v = label_validator()
    state, _, _ = v.validate("cat", 3)  # ty: ignore[not-iterable]
    assert state == QtGui.QValidator.State.Acceptable


def test_label_validator_rejects_single_char() -> None:
    # A single non-whitespace character is not yet an acceptable label.
    v = label_validator()
    state, _, _ = v.validate("c", 1)  # ty: ignore[not-iterable]
    assert state != QtGui.QValidator.State.Acceptable


# ---------------------------------------------------------------------------
# new_icon
# ---------------------------------------------------------------------------


def test_new_icon_returns_qicon(qtbot: QtBot) -> None:
    icon = new_icon("icon")
    assert isinstance(icon, QtGui.QIcon)


def test_new_icon_with_explicit_png_suffix(qtbot: QtBot) -> None:
    icon = new_icon("icon.png")
    assert isinstance(icon, QtGui.QIcon)


def test_new_icon_with_path_that_includes_subdir(qtbot: QtBot) -> None:
    icon = new_icon("phosphor/info.svg")
    assert isinstance(icon, QtGui.QIcon)


# ---------------------------------------------------------------------------
# color-theme icon tinting
# ---------------------------------------------------------------------------


def _set_window_text(app: QtWidgets.QApplication, color: QtGui.QColor) -> None:
    palette = app.palette()
    palette.setColor(
        QtGui.QPalette.ColorGroup.Normal, QtGui.QPalette.ColorRole.WindowText, color
    )
    app.setPalette(palette)


def test_tinted_svg_engine_renders_window_text_color(
    qapp: QtWidgets.QApplication,
) -> None:
    original = qapp.palette()
    try:
        _set_window_text(qapp, QtGui.QColor(255, 0, 0))
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


def test_new_icon_tints_monochrome_icon_to_palette(
    qapp: QtWidgets.QApplication,
) -> None:
    original = qapp.palette()
    try:
        icon = new_icon("phosphor/polygon.svg")  # authored with fill="currentColor"
        _set_window_text(qapp, QtGui.QColor(255, 0, 0))
        red = icon.pixmap(QtCore.QSize(24, 24)).toImage()
        _set_window_text(qapp, QtGui.QColor(0, 0, 255))
        blue = icon.pixmap(QtCore.QSize(24, 24)).toImage()
        assert red != blue
    finally:
        qapp.setPalette(original)


def test_new_icon_keeps_accent_icon_fixed(qapp: QtWidgets.QApplication) -> None:
    original = qapp.palette()
    try:
        icon = new_icon("phosphor/floppy-disk.svg")  # baked accent color, not tinted
        _set_window_text(qapp, QtGui.QColor(255, 0, 0))
        a = icon.pixmap(QtCore.QSize(24, 24)).toImage()
        _set_window_text(qapp, QtGui.QColor(0, 255, 0))
        b = icon.pixmap(QtCore.QSize(24, 24)).toImage()
        assert a == b
    finally:
        qapp.setPalette(original)


# ---------------------------------------------------------------------------
# new_action
# ---------------------------------------------------------------------------


def test_new_action_returns_qaction(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="Open")
    assert isinstance(action, QtGui.QAction)


def test_new_action_text(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="Save")
    assert action.text() == "Save"


def test_new_action_enabled_by_default(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X")
    assert action.isEnabled()


def test_new_action_disabled(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", enabled=False)
    assert not action.isEnabled()


def test_new_action_not_checkable_by_default(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X")
    assert not action.isCheckable()


def test_new_action_checkable(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", checkable=True)
    assert action.isCheckable()


def test_new_action_not_checked_by_default(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", checkable=True)
    assert not action.isChecked()


def test_new_action_checked(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", checkable=True, checked=True)
    assert action.isChecked()


def test_new_action_shortcut_string(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", shortcut="Ctrl+S")
    assert action.shortcut().toString() == "Ctrl+S"


def test_new_action_shortcut_list(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", shortcut=["Ctrl+S", "Ctrl+W"])
    keys = [s.toString() for s in action.shortcuts()]
    assert "Ctrl+S" in keys
    assert "Ctrl+W" in keys


def test_new_action_shortcut_tuple(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", shortcut=("Ctrl+S", "Ctrl+W"))
    keys = [s.toString() for s in action.shortcuts()]
    assert "Ctrl+S" in keys
    assert "Ctrl+W" in keys


def test_new_action_tip(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", tip="My tip")
    assert action.toolTip() == "My tip"
    assert action.statusTip() == "My tip"


def test_new_action_no_tip_by_default(qtbot: QtBot) -> None:
    # Qt 6 behavior: toolTip() falls back to the action text when no tip is set;
    # statusTip() returns empty string.
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X")
    assert action.toolTip() == "X"
    assert action.statusTip() == ""


def test_new_action_with_icon_sets_icon_text(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    # Use an icon file that actually exists so Qt loads it as non-null.
    action = new_action(parent, text="Save File", icon="ai-box.svg")
    # multi-word labels are presented so words are not shown on a single unbroken line
    icon_text = action.iconText()
    assert icon_text != "Save File"  # must not be the original single-line text
    assert "Save" in icon_text
    assert "File" in icon_text
    assert not action.icon().isNull()


def test_new_action_slot(qtbot: QtBot) -> None:
    calls: list[bool] = []
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    action = new_action(parent, text="X", slot=lambda: calls.append(True))
    action.trigger()
    assert calls == [True]


# ---------------------------------------------------------------------------
# add_actions
# ---------------------------------------------------------------------------


def test_add_actions_adds_qaction_to_menu(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    menu = QtWidgets.QMenu(parent)
    action = QtGui.QAction("Cut", parent)
    add_actions(menu, [action])
    assert action in menu.actions()


def test_add_actions_none_adds_separator_to_menu(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    menu = QtWidgets.QMenu(parent)
    action = QtGui.QAction("Cut", parent)
    add_actions(menu, [action, None])
    separators = [a for a in menu.actions() if a.isSeparator()]
    assert len(separators) == 1


def test_add_actions_submenu_to_menu(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    menu = QtWidgets.QMenu(parent)
    submenu = QtWidgets.QMenu("Sub", parent)
    add_actions(menu, [submenu])
    # QMenu added as submenu appears in actions list
    titles = [a.text() for a in menu.actions()]
    assert "Sub" in titles


def test_add_actions_adds_qaction_to_toolbar(qtbot: QtBot) -> None:
    toolbar = QtWidgets.QToolBar()
    qtbot.addWidget(toolbar)
    action = QtGui.QAction("Copy", toolbar)
    add_actions(toolbar, [action])
    assert action in toolbar.actions()


def test_add_actions_none_adds_separator_to_toolbar(qtbot: QtBot) -> None:
    toolbar = QtWidgets.QToolBar()
    qtbot.addWidget(toolbar)
    action = QtGui.QAction("Copy", toolbar)
    add_actions(toolbar, [action, None])
    separators = [a for a in toolbar.actions() if a.isSeparator()]
    assert len(separators) == 1


def test_add_actions_empty_sequence(qtbot: QtBot) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    menu = QtWidgets.QMenu(parent)
    add_actions(menu, [])
    assert menu.actions() == []
