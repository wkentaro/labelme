from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._widgets.label_list_widget import format_label_with_color_dot
from labelme._widgets.unique_label_qlist_widget import UniqueLabelQListWidget


@pytest.fixture()
def widget(qtbot: QtBot) -> UniqueLabelQListWidget:
    widget = UniqueLabelQListWidget()
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    widget.show()
    return widget


@pytest.fixture()
def selected_widget(widget: UniqueLabelQListWidget) -> UniqueLabelQListWidget:
    widget.add_label_item(label="cat", color=(255, 0, 0))
    widget.setCurrentRow(0)
    assert widget.selectedItems()
    return widget


def test_add_label_item_is_findable_and_rendered(
    widget: UniqueLabelQListWidget,
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0))

    item = widget.find_label_item(label="cat")
    assert item is not None
    assert item.text() == format_label_with_color_dot(text="cat", color=(255, 0, 0))


def test_add_label_item_rejects_duplicate_label(
    widget: UniqueLabelQListWidget,
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0))

    with pytest.raises(ValueError, match="already exists"):
        widget.add_label_item(label="cat", color=(0, 255, 0))

    assert widget.count() == 1


def test_find_label_item_returns_none_for_unknown_label(
    widget: UniqueLabelQListWidget,
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0))

    assert widget.find_label_item(label="dog") is None


def test_escape_key_clears_selection(
    qtbot: QtBot, selected_widget: UniqueLabelQListWidget
) -> None:
    qtbot.keyClick(selected_widget, Qt.Key.Key_Escape)

    assert selected_widget.selectedItems() == []


def test_press_on_empty_area_clears_selection(
    qtbot: QtBot, selected_widget: UniqueLabelQListWidget
) -> None:
    empty_pos = selected_widget.viewport().rect().bottomRight()
    assert not selected_widget.indexAt(empty_pos).isValid()

    qtbot.mouseClick(
        selected_widget.viewport(), Qt.MouseButton.LeftButton, pos=empty_pos
    )

    assert selected_widget.selectedItems() == []
