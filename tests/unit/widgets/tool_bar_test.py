from __future__ import annotations

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._widgets.tool_bar import ToolBar

# Qt automatically adds an internal extension/overflow button to every QToolBar.
# Filter it out when counting user-added buttons.
_EXT_BUTTON_NAME = "qt_toolbar_ext_button"


def _user_buttons(toolbar: ToolBar) -> list[QtWidgets.QToolButton]:
    return [
        b
        for b in toolbar.findChildren(QtWidgets.QToolButton)
        if b.objectName() != _EXT_BUTTON_NAME
    ]


def _make_action(text: str) -> QtGui.QAction:
    # Create without a parent so the action outlives any ephemeral container.
    return QtGui.QAction(text)


@pytest.fixture()
def actions() -> list[QtGui.QAction | None]:
    return [
        _make_action("Alpha"),
        _make_action("Beta"),
        None,
        _make_action("Gamma"),
    ]


@pytest.fixture()
def toolbar_h(qtbot: QtBot, actions: list[QtGui.QAction | None]) -> ToolBar:
    tb = ToolBar(
        title="Test",
        actions=actions,
        orientation=Qt.Orientation.Horizontal,
    )
    qtbot.addWidget(tb)
    return tb


@pytest.fixture()
def toolbar_v(qtbot: QtBot, actions: list[QtGui.QAction | None]) -> ToolBar:
    tb = ToolBar(
        title="Test",
        actions=actions,
        orientation=Qt.Orientation.Vertical,
    )
    qtbot.addWidget(tb)
    return tb


# --- object name ---


def test_toolbar_object_name_uses_title(qtbot: QtBot) -> None:
    tb = ToolBar(title="MyBar", actions=[])
    qtbot.addWidget(tb)
    assert tb.objectName() == "MyBarToolBar"


# --- movable / floatable ---


def test_toolbar_is_not_movable(toolbar_h: ToolBar) -> None:
    assert not toolbar_h.isMovable()


def test_toolbar_is_not_floatable(toolbar_h: ToolBar) -> None:
    assert not toolbar_h.isFloatable()


# --- frameless window flag ---


def test_toolbar_has_frameless_window_flag(toolbar_h: ToolBar) -> None:
    assert toolbar_h.windowFlags() & Qt.WindowType.FramelessWindowHint


# --- layout spacing / margins ---


def test_toolbar_layout_spacing_is_zero(toolbar_h: ToolBar) -> None:
    layout = toolbar_h.layout()
    assert layout is not None
    assert layout.spacing() == 0


def test_toolbar_layout_contents_margins_all_zero(toolbar_h: ToolBar) -> None:
    layout = toolbar_h.layout()
    assert layout is not None
    m = layout.contentsMargins()
    assert m.left() == 0
    assert m.top() == 0
    assert m.right() == 0
    assert m.bottom() == 0


# --- orientation ---


def test_toolbar_default_orientation_is_horizontal(toolbar_h: ToolBar) -> None:
    assert toolbar_h.orientation() == Qt.Orientation.Horizontal


def test_toolbar_vertical_orientation(toolbar_v: ToolBar) -> None:
    assert toolbar_v.orientation() == Qt.Orientation.Vertical


# --- tool button style ---


def test_toolbar_default_button_style_is_text_under_icon(toolbar_h: ToolBar) -> None:
    assert toolbar_h.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextUnderIcon


def test_toolbar_custom_button_style(qtbot: QtBot) -> None:
    tb = ToolBar(
        title="T",
        actions=[],
        button_style=Qt.ToolButtonStyle.ToolButtonIconOnly,
    )
    qtbot.addWidget(tb)
    assert tb.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly


# --- actions produce QToolButton children ---


def test_toolbar_actions_create_tool_buttons(toolbar_h: ToolBar) -> None:
    # 3 real actions + None separator = 3 user buttons (separator is not a button)
    buttons = _user_buttons(toolbar_h)
    assert len(buttons) == 3


def test_toolbar_tool_buttons_inherit_button_style(toolbar_h: ToolBar) -> None:
    for btn in _user_buttons(toolbar_h):
        assert btn.toolButtonStyle() == toolbar_h.toolButtonStyle()


def test_toolbar_tool_buttons_have_default_action(toolbar_h: ToolBar) -> None:
    for btn in _user_buttons(toolbar_h):
        assert btn.defaultAction() is not None


# --- separator ---


def test_toolbar_none_action_inserts_separator(toolbar_h: ToolBar) -> None:
    separators = [a for a in toolbar_h.actions() if a.isSeparator()]
    assert len(separators) == 1


# --- QWidgetAction bypasses QToolButton wrapping ---


def test_toolbar_widget_action_not_wrapped_in_tool_button(qtbot: QtBot) -> None:
    inner = QtWidgets.QLabel("label")
    wa = QtWidgets.QWidgetAction(None)  # ty: ignore[invalid-argument-type]
    wa.setDefaultWidget(inner)

    tb = ToolBar(title="WA", actions=[wa])
    qtbot.addWidget(tb)

    # QWidgetAction is added via super().addAction(), not wrapped in a QToolButton.
    buttons = _user_buttons(tb)
    assert len(buttons) == 0


# --- button style change propagates to existing buttons ---


def test_toolbar_button_style_change_propagates(toolbar_h: ToolBar) -> None:
    toolbar_h.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    for btn in _user_buttons(toolbar_h):
        assert btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly


# --- vertical toolbar: buttons equalized ---


def test_toolbar_vertical_buttons_equal_min_width(toolbar_v: ToolBar) -> None:
    buttons = _user_buttons(toolbar_v)
    assert len(buttons) >= 2
    widths = [btn.minimumWidth() for btn in buttons]
    assert len(set(widths)) == 1, f"Button minimum widths not equal: {widths}"
    assert widths[0] > 0


def test_toolbar_horizontal_buttons_not_equalized(toolbar_h: ToolBar) -> None:
    # Horizontal toolbar does NOT call _equalize_button_widths; minimumWidth stays 0.
    for btn in _user_buttons(toolbar_h):
        assert btn.minimumWidth() == 0


# --- font scaling when font_base is provided ---


def test_toolbar_font_scaled_when_font_base_given(qtbot: QtBot) -> None:
    base_font = QtGui.QFont()
    base_font.setPointSizeF(16.0)

    tb = ToolBar(title="F", actions=[], font_base=base_font)
    qtbot.addWidget(tb)

    assert tb.font().pointSizeF() < base_font.pointSizeF()


def test_toolbar_no_font_scaling_without_font_base(qtbot: QtBot) -> None:
    tb = ToolBar(title="F2", actions=[], font_base=None)
    qtbot.addWidget(tb)

    # Without font_base the toolbar uses the application default font.
    app = QtWidgets.QApplication.instance()
    assert app is not None
    app_point_size = app.font().pointSizeF()  # ty: ignore[unresolved-attribute]
    assert tb.font().pointSizeF() == pytest.approx(app_point_size, abs=0.5)


# --- empty action list is valid ---


def test_toolbar_empty_actions(qtbot: QtBot) -> None:
    tb = ToolBar(title="Empty", actions=[])
    qtbot.addWidget(tb)
    assert len(_user_buttons(tb)) == 0
