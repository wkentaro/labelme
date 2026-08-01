from __future__ import annotations

from typing import Final

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QStyle
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._widgets.label_list_widget import HTMLDelegate
from labelme._widgets.label_list_widget import LabelListWidget
from labelme._widgets.label_list_widget import LabelListWidgetItem
from labelme._widgets.label_list_widget import format_label_with_color_dot
from labelme._widgets.label_list_widget import format_shape_label


def _paint_label(
    option: QtWidgets.QStyleOptionViewItem, text: str, width: int
) -> QtGui.QImage:
    model = QtGui.QStandardItemModel()
    model.appendRow(QtGui.QStandardItem(text))

    image = QtGui.QImage(width, 24, QtGui.QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QtGui.QPainter(image)
    HTMLDelegate().paint(painter, option, model.index(0, 0))
    painter.end()
    return image


def _has_ink_from(image: QtGui.QImage, start_x: int) -> bool:
    for x in range(start_x, image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y) != QtGui.QColor(Qt.GlobalColor.white):
                return True
    return False


def test_html_delegate_does_not_clip_label_when_text_subrect_collapses(
    qtbot: QtBot,
) -> None:
    option = QtWidgets.QStyleOptionViewItem()
    # A narrow item rect emulates the styles (e.g. Adwaita) whose text sub-rect
    # collapses because the delegate empties opt.text before measuring it.
    option.rect = QtCore.QRect(0, 0, 6, 24)
    option.palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QtGui.QColor("black")
    )
    image = _paint_label(option=option, text="LabelText " * 8, width=400)

    # The collapsed sub-rect is only 6px wide; ink well past it (x >= 20) proves
    # the widened clip rect let the label render instead of clipping it away.
    assert _has_ink_from(image, start_x=20)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected,
            (QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText),
        ),
        (
            QStyle.StateFlag.State_Enabled
            | QStyle.StateFlag.State_Selected
            | QStyle.StateFlag.State_Active,
            (QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText),
        ),
        (
            QStyle.StateFlag.State_Selected,
            (QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText),
        ),
        (
            QStyle.StateFlag.State_Enabled,
            (QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text),
        ),
        (
            QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active,
            (QPalette.ColorGroup.Active, QPalette.ColorRole.Text),
        ),
        (
            QStyle.StateFlag.State_None,
            (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text),
        ),
    ],
    ids=[
        "selected_unfocused_view",
        "selected_focused_view",
        "selected_disabled_row",
        "unselected_unfocused_view",
        "unselected_focused_view",
        "unselected_disabled_row",
    ],
)
def test_html_delegate_takes_text_color_from_the_state_color_group(
    qtbot: QtBot,
    state: QStyle.StateFlag,
    expected: tuple[QPalette.ColorGroup, QPalette.ColorRole],
) -> None:
    # A view that does not hold focus loses State_Active, so the style fills the
    # row from the Inactive group; the text has to come from that same group or
    # it lands as white-on-pale-gray.
    INK: Final = {
        (QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText): "#ff0000",
        (QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText): "#0000ff",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText): "#00ff00",
        (QPalette.ColorGroup.Active, QPalette.ColorRole.Text): "#ff00ff",
        (QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text): "#00ffff",
        (QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text): "#ffff00",
    }

    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, 200, 24)
    option.state = state
    for (group, role), color in INK.items():
        option.palette.setColor(group, role, QtGui.QColor(color))
    image = _paint_label(option=option, text="bottle", width=200)

    inks = {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
    }
    assert INK[expected] in inks
    assert inks.isdisjoint(set(INK.values()) - {INK[expected]})


@pytest.fixture()
def widget(qtbot: QtBot) -> LabelListWidget:
    widget = LabelListWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    widget.show()
    return widget


@pytest.fixture()
def selected_pair(
    widget: LabelListWidget,
) -> tuple[LabelListWidgetItem, LabelListWidgetItem]:
    item_a = LabelListWidgetItem(text="cat")
    item_b = LabelListWidgetItem(text="dog")
    widget.add_item(item_a)
    widget.add_item(item_b)
    widget.select_item(item_a)
    widget.select_item(item_b)
    return item_a, item_b


def _item_center(widget: LabelListWidget, item: LabelListWidgetItem) -> QtCore.QPoint:
    model = widget.model()
    assert model is not None
    return widget.visualRect(model.index(item.row(), 0)).center()


def _press_on_item(
    qtbot: QtBot, widget: LabelListWidget, item: LabelListWidgetItem
) -> None:
    qtbot.mousePress(
        widget.viewport(),
        Qt.MouseButton.LeftButton,
        pos=_item_center(widget=widget, item=item),
    )


def test_selection_at_press_drops_items_removed_before_release(
    qtbot: QtBot, widget: LabelListWidget
) -> None:
    # A context menu or drag can consume the mouse release, so the press
    # snapshot legally outlives the items it references (e.g. right-click
    # -> Delete on macOS, where the menu opens on press).
    item = LabelListWidgetItem(text="cat")
    widget.add_item(item)
    widget.select_item(item)
    _press_on_item(qtbot=qtbot, widget=widget, item=item)

    widget.remove_item(item)
    replacement = LabelListWidgetItem(text="cat")
    widget.add_item(replacement)

    selection_at_press = widget.selection_at_press()
    assert replacement not in selection_at_press
    assert selection_at_press == ()


def test_mouse_release_after_item_removal_does_not_crash(
    qtbot: QtBot,
    widget: LabelListWidget,
    selected_pair: tuple[LabelListWidgetItem, LabelListWidgetItem],
) -> None:
    item_a, _ = selected_pair
    _press_on_item(qtbot=qtbot, widget=widget, item=item_a)

    widget.remove_item(item_a)
    release_pos = widget.viewport().rect().center()
    qtbot.mouseRelease(widget.viewport(), Qt.MouseButton.LeftButton, pos=release_pos)

    assert widget.selection_at_press() == ()


def test_selection_at_press_returns_live_multi_selection(
    qtbot: QtBot,
    widget: LabelListWidget,
    selected_pair: tuple[LabelListWidgetItem, LabelListWidgetItem],
) -> None:
    item_a, item_b = selected_pair
    _press_on_item(qtbot=qtbot, widget=widget, item=item_a)

    assert set(widget.selection_at_press()) == {item_a, item_b}


def test_release_keeps_multi_selection_when_press_toggled_checkbox(
    qtbot: QtBot,
    widget: LabelListWidget,
    selected_pair: tuple[LabelListWidgetItem, LabelListWidgetItem],
) -> None:
    item_a, item_b = selected_pair
    _press_on_item(qtbot=qtbot, widget=widget, item=item_a)
    # The view toggles the check state during the click when the press lands
    # on the checkbox; emulate that toggle directly since the checkbox
    # position depends on the platform style.
    item_a.setCheckState(Qt.CheckState.Unchecked)
    qtbot.mouseRelease(
        widget.viewport(),
        Qt.MouseButton.LeftButton,
        pos=_item_center(widget=widget, item=item_a),
    )

    assert set(widget.selected_items()) == {item_a, item_b}


@pytest.mark.parametrize(
    ("text", "color", "expected"),
    [
        ("cat", (1, 2, 3), 'cat <font color="#010203">●</font>'),
        ('<b>&"', (0, 0, 0), '&lt;b&gt;&amp;&quot; <font color="#000000">●</font>'),
    ],
    ids=["zero_pads_each_channel", "escapes_html_in_text"],
)
def test_format_label_with_color_dot(
    text: str, color: tuple[int, int, int], expected: str
) -> None:
    assert format_label_with_color_dot(text=text, color=color) == expected


@pytest.mark.parametrize(
    ("shape", "fill_rgb", "expected"),
    [
        (Shape(label="cat"), (255, 0, 0), 'cat <font color="#ff0000">●</font>'),
        (
            Shape(label="cat", group_id=3),
            (0, 0, 0),
            'cat (3) <font color="#000000">●</font>',
        ),
        (
            Shape(label="cat", group_id=0),
            (0, 0, 0),
            'cat (0) <font color="#000000">●</font>',
        ),
        (
            Shape(
                label="cat",
                flags={"occluded": True, "truncated": False, "difficult": True},
            ),
            (0, 0, 0),
            'cat [occluded, difficult] <font color="#000000">●</font>',
        ),
        (
            Shape(label="cat", flags={"occluded": False}),
            (0, 0, 0),
            'cat <font color="#000000">●</font>',
        ),
        (
            Shape(label="cat", group_id=3, flags={"occluded": True}),
            (0, 0, 0),
            'cat (3) [occluded] <font color="#000000">●</font>',
        ),
        (
            Shape(label="<b>", group_id=1),
            (0, 0, 0),
            '&lt;b&gt; (1) <font color="#000000">●</font>',
        ),
    ],
    ids=[
        "bare_label_when_no_group_or_flags",
        "appends_group_id",
        "appends_group_id_zero",
        "appends_only_enabled_flags_in_order",
        "omits_brackets_when_no_flag_is_enabled",
        "combines_group_id_before_flags",
        "escapes_html_in_composed_text",
    ],
)
def test_format_shape_label(
    shape: Shape, fill_rgb: tuple[int, int, int], expected: str
) -> None:
    assert format_shape_label(shape=shape, fill_rgb=fill_rgb) == expected
