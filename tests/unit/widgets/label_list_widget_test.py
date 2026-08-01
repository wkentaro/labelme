from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QStyle
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._widgets.label_list_widget import LabelListWidget
from labelme._widgets.label_list_widget import LabelListWidgetItem
from labelme._widgets.label_list_widget import format_shape_label


def _paint_item(
    delegate: QtWidgets.QAbstractItemDelegate,
    item: LabelListWidgetItem,
    option: QtWidgets.QStyleOptionViewItem,
) -> QtGui.QImage:
    model = QtGui.QStandardItemModel()
    model.appendRow(item)
    image = QtGui.QImage(200, 24, QtGui.QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QtGui.QPainter(image)
    delegate.paint(painter, option, model.index(0, 0))
    painter.end()
    return image


def _pixels_with_color(image: QtGui.QImage, color: QtGui.QColor) -> list[QtCore.QPoint]:
    return [
        QtCore.QPoint(x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y) == color
    ]


@pytest.fixture()
def widget(qtbot: QtBot) -> LabelListWidget:
    widget = LabelListWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    widget.show()
    return widget


def test_label_list_text_matches_stock_delegate_when_selected_unfocused(
    widget: LabelListWidget,
) -> None:
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, 200, 24)
    option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected
    option.palette.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.HighlightedText,
        QtGui.QColor("red"),
    )
    option.palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.HighlightedText,
        QtGui.QColor("blue"),
    )

    item = LabelListWidgetItem(shape=Shape(label="bottle"))
    item.set_label(text="bottle", color=(0, 255, 0))
    actual = _paint_item(delegate=widget.itemDelegate(), item=item, option=option)
    expected = _paint_item(
        delegate=QtWidgets.QStyledItemDelegate(),
        item=LabelListWidgetItem(text="bottle", shape=Shape(label="bottle")),
        option=option,
    )

    label_pixels = _pixels_with_color(image=expected, color=QtGui.QColor("blue"))
    dot_pixels = _pixels_with_color(image=actual, color=QtGui.QColor(0, 255, 0))
    assert label_pixels
    assert dot_pixels
    label_right = max(point.x() for point in label_pixels)
    assert label_right < min(point.x() for point in dot_pixels)
    prefix = QtCore.QRect(0, 0, label_right + 1, actual.height())
    assert actual.copy(prefix) == expected.copy(prefix)


def test_color_dot_is_painted_without_a_text_colored_fringe(
    widget: LabelListWidget,
) -> None:
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, 200, 24)
    option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        option.palette.setColor(
            group, QPalette.ColorRole.Highlight, QtGui.QColor("blue")
        )
        option.palette.setColor(
            group, QPalette.ColorRole.HighlightedText, QtGui.QColor("white")
        )

    item = LabelListWidgetItem(shape=Shape(label="bottle"))
    item.set_label(text="bottle", color=(255, 0, 0))
    image = _paint_item(delegate=widget.itemDelegate(), item=item, option=option)

    dot_pixels = _pixels_with_color(image=image, color=QtGui.QColor(255, 0, 0))
    assert dot_pixels
    # Only the dot blended into the highlight belongs around the dot, and
    # neither carries a green channel. Any green there is the white glyph Qt
    # paints for a dot left in the item text, showing out from underneath.
    xs = [point.x() for point in dot_pixels]
    ys = [point.y() for point in dot_pixels]
    assert not [
        (x, y)
        for x in range(min(xs) - 1, max(xs) + 2)
        for y in range(min(ys) - 1, max(ys) + 2)
        if image.pixelColor(x, y).green() != 0
    ]


def test_label_list_item_clone_preserves_color_dot(widget: LabelListWidget) -> None:
    item = LabelListWidgetItem(shape=Shape(label="cat"))
    item.set_label(text="cat", color=(0, 255, 0))
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, 200, 24)

    image = _paint_item(
        delegate=widget.itemDelegate(),
        item=item.clone(),
        option=option,
    )

    assert _pixels_with_color(image=image, color=QtGui.QColor(0, 255, 0))


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
    ("shape", "expected"),
    [
        (Shape(label="cat"), "cat"),
        (Shape(label="cat", group_id=3), "cat (3)"),
        (Shape(label="cat", group_id=0), "cat (0)"),
        (
            Shape(
                label="cat",
                flags={"occluded": True, "truncated": False, "difficult": True},
            ),
            "cat [occluded, difficult]",
        ),
        (Shape(label="cat", flags={"occluded": False}), "cat"),
        (
            Shape(label="cat", group_id=3, flags={"occluded": True}),
            "cat (3) [occluded]",
        ),
        (Shape(label="<b>", group_id=1), "<b> (1)"),
    ],
    ids=[
        "bare_label_when_no_group_or_flags",
        "appends_group_id",
        "appends_group_id_zero",
        "appends_only_enabled_flags_in_order",
        "omits_brackets_when_no_flag_is_enabled",
        "combines_group_id_before_flags",
        "keeps_markup_literal",
    ],
)
def test_format_shape_label(shape: Shape, expected: str) -> None:
    assert format_shape_label(shape=shape) == expected
