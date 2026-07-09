from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._widgets.label_list_widget import HTMLDelegate
from labelme._widgets.label_list_widget import LabelListWidget
from labelme._widgets.label_list_widget import LabelListWidgetItem
from labelme._widgets.label_list_widget import format_label_with_color_dot
from labelme._widgets.label_list_widget import format_shape_label


def _has_ink_from(image: QtGui.QImage, start_x: int) -> bool:
    for x in range(start_x, image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y) != QtGui.QColor(Qt.GlobalColor.white):
                return True
    return False


def test_html_delegate_does_not_clip_label_when_text_subrect_collapses(
    qtbot: QtBot,
) -> None:
    model = QtGui.QStandardItemModel()
    model.appendRow(QtGui.QStandardItem("LabelText " * 8))
    index = model.index(0, 0)

    delegate = HTMLDelegate()

    image = QtGui.QImage(400, 24, QtGui.QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QtGui.QPainter(image)

    option = QtWidgets.QStyleOptionViewItem()
    # A narrow item rect emulates the styles (e.g. Adwaita) whose text sub-rect
    # collapses because the delegate empties opt.text before measuring it.
    option.rect = QtCore.QRect(0, 0, 6, 24)
    option.palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QtGui.QColor("black")
    )
    delegate.paint(painter, option, index)
    painter.end()

    # The collapsed sub-rect is only 6px wide; ink well past it (x >= 20) proves
    # the widened clip rect let the label render instead of clipping it away.
    assert _has_ink_from(image, start_x=20)


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
