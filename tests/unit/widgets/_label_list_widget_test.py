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
from labelme._widgets._label_list_widget import LabelListWidget
from labelme._widgets._label_list_widget import LabelListWidgetItem
from labelme._widgets._label_list_widget import _ItemModel
from labelme._widgets._label_list_widget import format_shape_label


def _paint_item(
    *,
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


def _pixels_with_color(
    *, image: QtGui.QImage, color: QtGui.QColor
) -> list[QtCore.QPoint]:
    return [
        QtCore.QPoint(x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).rgb() == color.rgb()
    ]


@pytest.fixture()
def widget(*, qtbot: QtBot) -> LabelListWidget:
    widget = LabelListWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    widget.show()
    return widget


def test_label_list_text_matches_stock_delegate_when_selected_unfocused(
    *,
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

    def stock(text: str) -> QtGui.QImage:
        return _paint_item(
            delegate=QtWidgets.QStyledItemDelegate(),
            item=LabelListWidgetItem(text=text, shape=Shape(label="bottle")),
            option=option,
        )

    # The swatch takes the slot of a leading em space; the text after it
    # must render as the stock delegate renders it. The label is found as
    # what its text adds to the row, since a style may draw the checkbox in
    # a color close to the text.
    expected = stock("\u2003bottle")
    blank = stock("\u2003")
    label_left = min(
        x
        for x in range(expected.width())
        for y in range(expected.height())
        if expected.pixel(x, y) != blank.pixel(x, y)
    )
    swatch_pixels = _pixels_with_color(image=actual, color=QtGui.QColor(0, 255, 0))
    assert swatch_pixels
    assert max(point.x() for point in swatch_pixels) < label_left
    text = QtCore.QRect(label_left, 0, actual.width() - label_left, actual.height())
    assert actual.copy(text) == expected.copy(text)


def test_lock_leaves_the_swatch_column_in_place(*, widget: LabelListWidget) -> None:
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, 200, 24)
    option.state = QStyle.StateFlag.State_Enabled

    def swatch_xs(*, locked: bool) -> set[int]:
        item = LabelListWidgetItem(shape=Shape(label="bottle", locked=locked))
        item.set_label(text="bottle", color=(0, 255, 0))
        image = _paint_item(delegate=widget.itemDelegate(), item=item, option=option)
        return {
            point.x()
            for point in _pixels_with_color(image=image, color=QtGui.QColor(0, 255, 0))
        }

    unlocked = swatch_xs(locked=False)
    assert unlocked
    assert swatch_xs(locked=True) == unlocked


def test_swatch_uses_widget_aware_checkbox_layout(*, widget: LabelListWidget) -> None:
    class InsetStyle(QtWidgets.QProxyStyle):
        def subElementRect(
            self,
            element: QStyle.SubElement,
            option: QtWidgets.QStyleOption,
            target: QtWidgets.QWidget | None = None,
            /,
        ) -> QtCore.QRect:
            rect = super().subElementRect(element, option, target or widget)
            if target is widget:
                if element == QStyle.SubElement.SE_ItemViewItemText:
                    rect.translate(6, 0)
                elif element == QStyle.SubElement.SE_ItemViewItemCheckIndicator:
                    rect.translate(0, 2)
            return rect

    style = InsetStyle("Fusion")
    style.setParent(widget)
    widget.setStyle(style)
    item = LabelListWidgetItem(shape=Shape(label="bottle"))
    item.set_label(text="bottle", color=(0, 255, 0))
    widget.add_item(item=item)
    index = widget.model().index(0, 0)
    delegate = widget.itemDelegate()
    assert isinstance(delegate, QtWidgets.QStyledItemDelegate)
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, 200, 24)
    option.widget = widget
    option.state = QStyle.StateFlag.State_Enabled
    delegate.initStyleOption(option, index)

    image = _paint_item(delegate=delegate, item=item.clone(), option=option)
    pixels = _pixels_with_color(image=image, color=QtGui.QColor(0, 255, 0))
    checkbox = style.subElementRect(
        QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, widget
    )
    text = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, widget)
    assert min(point.x() for point in pixels) >= text.left()
    ys = [point.y() for point in pixels]
    center_y = (min(ys) + max(ys) + 1) / 2
    assert center_y == pytest.approx(QtCore.QRectF(checkbox).center().y(), abs=0.5)


def test_label_list_item_clone_preserves_color_swatch(
    *, widget: LabelListWidget
) -> None:
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


@pytest.mark.parametrize(
    "label",
    [
        "a_very_long_label_that_the_dock_cuts_off (3) [occluded]",
        "<b>",
        "<b>cat</b>",
        "a & b",
    ],
)
def test_label_list_item_tooltip_shows_full_label(*, label: str) -> None:
    item = LabelListWidgetItem(shape=Shape(label=label))
    item.set_label(text=label, color=(0, 255, 0))

    document = QtGui.QTextDocument()
    document.setHtml(item.toolTip())
    assert QtGui.Qt.mightBeRichText(item.toolTip())
    assert document.toPlainText() == label


@pytest.fixture()
def selected_pair(
    *,
    widget: LabelListWidget,
) -> tuple[LabelListWidgetItem, LabelListWidgetItem]:
    item_a = LabelListWidgetItem(text="cat")
    item_b = LabelListWidgetItem(text="dog")
    widget.add_item(item=item_a)
    widget.add_item(item=item_b)
    widget.select_item(item=item_a)
    widget.select_item(item=item_b)
    return item_a, item_b


def _item_center(
    *, widget: LabelListWidget, item: LabelListWidgetItem
) -> QtCore.QPoint:
    model = widget.model()
    assert model is not None
    return widget.visualRect(model.index(item.row(), 0)).center()


def _press_on_item(
    *, qtbot: QtBot, widget: LabelListWidget, item: LabelListWidgetItem
) -> None:
    qtbot.mousePress(
        widget.viewport(),
        Qt.MouseButton.LeftButton,
        pos=_item_center(widget=widget, item=item),
    )


def test_selection_at_press_drops_items_removed_before_release(
    *, qtbot: QtBot, widget: LabelListWidget
) -> None:
    # A context menu or drag can consume the mouse release, so the press
    # snapshot legally outlives the items it references (e.g. right-click
    # -> Delete on macOS, where the menu opens on press).
    item = LabelListWidgetItem(text="cat")
    widget.add_item(item=item)
    widget.select_item(item=item)
    _press_on_item(qtbot=qtbot, widget=widget, item=item)

    widget.remove_item(item=item)
    replacement = LabelListWidgetItem(text="cat")
    widget.add_item(item=replacement)

    selection_at_press = widget.selection_at_press()
    assert replacement not in selection_at_press
    assert selection_at_press == ()


def test_mouse_release_after_item_removal_does_not_crash(
    *,
    qtbot: QtBot,
    widget: LabelListWidget,
    selected_pair: tuple[LabelListWidgetItem, LabelListWidgetItem],
) -> None:
    item_a, _ = selected_pair
    _press_on_item(qtbot=qtbot, widget=widget, item=item_a)

    widget.remove_item(item=item_a)
    release_pos = widget.viewport().rect().center()
    qtbot.mouseRelease(widget.viewport(), Qt.MouseButton.LeftButton, pos=release_pos)

    assert widget.selection_at_press() == ()


def test_selection_at_press_returns_live_multi_selection(
    *,
    qtbot: QtBot,
    widget: LabelListWidget,
    selected_pair: tuple[LabelListWidgetItem, LabelListWidgetItem],
) -> None:
    item_a, item_b = selected_pair
    _press_on_item(qtbot=qtbot, widget=widget, item=item_a)

    assert set(widget.selection_at_press()) == {item_a, item_b}


def test_release_keeps_multi_selection_when_press_toggled_checkbox(
    *,
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
def test_format_shape_label(*, shape: Shape, expected: str) -> None:
    assert format_shape_label(shape=shape) == expected


def _model_texts(*, model: _ItemModel) -> list[str]:
    return [model.item(row).text() for row in range(model.rowCount())]


@pytest.fixture()
def item_model(
    *,
    qapp: QtWidgets.QApplication,  # noqa: ARG001 -- a fixture cannot use usefixtures
) -> _ItemModel:
    model = _ItemModel()
    model.setItemPrototype(LabelListWidgetItem())
    for text in ["a", "b", "c"]:
        model.setItem(model.rowCount(), 0, LabelListWidgetItem(text=text))
    return model


_DropIndicator = QtWidgets.QAbstractItemView.DropIndicatorPosition


def test_drag_indicates_insertion_between_shapes(*, widget: LabelListWidget) -> None:
    for text in "abc":
        widget.add_item(item=LabelListWidgetItem(text=text))
    # Synthetic drag events have no source widget; allow them through Qt's
    # source check while exercising its real drop-indicator calculation.
    widget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragDrop)
    model = widget.model()
    mime = model.mimeData([model.index(0, 0)])
    rect = widget.visualRect(model.index(1, 0))
    for offset, expected in [
        (-1, _DropIndicator.AboveItem),
        (1, _DropIndicator.BelowItem),
    ]:
        event = QtGui.QDragMoveEvent(
            rect.center() + QtCore.QPoint(0, offset),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        widget.dragMoveEvent(event)

        assert event.isAccepted()
        assert widget.dropIndicatorPosition() == expected


@pytest.mark.parametrize(
    ("selected", "indicator", "target", "expected"),
    [
        (["a", "b"], _DropIndicator.OnViewport, None, ["c", "a", "b"]),
        (["c"], _DropIndicator.AboveItem, "a", ["c", "a", "b"]),
        (["c"], _DropIndicator.OnItem, "a", ["a", "c", "b"]),
        (["a", "c"], _DropIndicator.BelowItem, "a", ["a", "c", "b"]),
    ],
    ids=["multi_row_to_end", "above_item", "on_item_inserts_after", "into_selection"],
)
def test_drop_moves_items_and_emits_item_dropped_once(
    *,
    widget: LabelListWidget,
    monkeypatch: pytest.MonkeyPatch,
    selected: list[str],
    indicator: _DropIndicator,
    target: str | None,
    expected: list[str],
) -> None:
    items = {
        text: LabelListWidgetItem(text=text, shape=Shape(label=text)) for text in "abc"
    }
    for item in items.values():
        widget.add_item(item=item)
    for text in selected:
        widget.select_item(item=items[text])
    fired: list[None] = []
    widget.item_dropped.connect(lambda: fired.append(None))
    # A synthetic drop never goes through dragMoveEvent, which is what sets
    # the indicator the handler reads.
    monkeypatch.setattr(widget, "dropIndicatorPosition", lambda: indicator)
    if target is None:
        pos = widget.visualRect(widget.model().index(2, 0)).bottomLeft()
        pos += QtCore.QPoint(0, 20)
    else:
        pos = _item_center(widget=widget, item=items[target])
    mime = QtCore.QMimeData()

    widget.dropEvent(
        QtGui.QDropEvent(
            QtCore.QPointF(pos),
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )

    assert [item.text() for item in widget] == expected
    moved_shapes = [item.shape() for item in widget]
    assert all(
        shape is items[text].shape()
        for shape, text in zip(moved_shapes, expected, strict=True)
    )
    assert fired == [None]


def test_remove_rows_emits_item_dropped(*, item_model: _ItemModel) -> None:
    fired: list[None] = []
    item_model.item_dropped.connect(lambda: fired.append(None))

    item_model.removeRows(0, 1)

    assert fired == [None]
    assert _model_texts(model=item_model) == ["b", "c"]
