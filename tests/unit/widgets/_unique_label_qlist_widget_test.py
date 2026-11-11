from __future__ import annotations

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._widgets._unique_label_qlist_widget import _UNUSED_ROLE
from labelme._widgets._unique_label_qlist_widget import UniqueLabelQListWidget


@pytest.fixture()
def edit_requests() -> list[None]:
    return []


@pytest.fixture()
def widget(*, qtbot: QtBot, edit_requests: list[None]) -> UniqueLabelQListWidget:
    widget = UniqueLabelQListWidget(
        on_edit_settings_labels=lambda: edit_requests.append(None),
        on_clear_unused=lambda: None,
    )
    qtbot.addWidget(widget)
    widget.resize(200, 200)
    widget.show()
    return widget


@pytest.fixture()
def selected_widget(*, widget: UniqueLabelQListWidget) -> UniqueLabelQListWidget:
    widget.add_label_item(label="cat", color=(255, 0, 0))
    widget.setCurrentItem(_item(widget=widget, label="cat"))
    assert widget.selectedItems()
    return widget


def test_add_label_item_is_findable_and_rendered(
    *,
    widget: UniqueLabelQListWidget,
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0))

    item = widget.find_label_item(label="cat")
    assert item is not None
    assert item.text() == "cat"
    image = widget.viewport().grab().toImage()
    assert any(
        image.pixelColor(x, y) == QtGui.QColor(255, 0, 0)
        for x in range(image.width())
        for y in range(image.height())
    )


def test_add_label_item_rejects_duplicate_label(
    *,
    widget: UniqueLabelQListWidget,
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0))

    with pytest.raises(ValueError, match="already exists"):
        widget.add_label_item(label="cat", color=(0, 255, 0))

    assert widget.labels() == ["cat"]


def test_find_label_item_returns_none_for_unknown_label(
    *,
    widget: UniqueLabelQListWidget,
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0))

    assert widget.find_label_item(label="dog") is None


def test_escape_key_clears_selection(
    *, qtbot: QtBot, selected_widget: UniqueLabelQListWidget
) -> None:
    qtbot.keyClick(selected_widget, Qt.Key.Key_Escape)

    assert selected_widget.selectedItems() == []


def test_press_on_empty_area_clears_selection(
    *, qtbot: QtBot, selected_widget: UniqueLabelQListWidget
) -> None:
    empty_pos = selected_widget.viewport().rect().bottomRight()
    assert not selected_widget.indexAt(empty_pos).isValid()

    qtbot.mouseClick(
        selected_widget.viewport(), Qt.MouseButton.LeftButton, pos=empty_pos
    )

    assert selected_widget.selectedItems() == []


def test_lookup_matches_literal_case_sensitive_labels(
    *, widget: UniqueLabelQListWidget
) -> None:
    labels = ["cat", "Cat", "cat*", "cat (1)", "<cat>&", "猫"]
    for label in labels:
        widget.add_label_item(label=label, color=(255, 0, 0))
    assert widget.labels() == labels
    for label in labels:
        item = widget.find_label_item(label=label)
        assert item is not None and item.text() == label
    assert widget.find_label_item(label="CAT") is None
    assert widget.find_label_item(label="cat?") is None


def _item(*, widget: UniqueLabelQListWidget, label: str) -> QtWidgets.QListWidgetItem:
    item = widget.find_label_item(label=label)
    assert item is not None
    return item


def _rows(*, widget: UniqueLabelQListWidget) -> list[str | None]:
    return [
        widget.item(row).data(Qt.ItemDataRole.UserRole) for row in range(widget.count())
    ]


def test_settings_labels_list_above_labels_found_in_annotations(
    *, widget: UniqueLabelQListWidget
) -> None:
    widget.add_label_item(label="car", color=(0, 0, 255))
    widget.add_label_item(label="cat", color=(255, 0, 0), from_settings=True)
    widget.add_label_item(label="dog", color=(0, 255, 0), from_settings=True)

    assert _rows(widget=widget) == [None, "cat", "dog", None, "car"]
    assert widget.labels() == ["cat", "dog", "car"]
    assert widget.label_index(label="car") == 2
    assert widget.label_index(label="bus") == 3


def test_section_headers_take_no_selection_or_completion(
    *, qtbot: QtBot, widget: UniqueLabelQListWidget
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0), from_settings=True)
    widget.add_label_item(label="car", color=(0, 0, 255))
    widget.setCurrentItem(_item(widget=widget, label="cat"))

    qtbot.keyClick(widget, Qt.Key.Key_Down)

    assert widget.selectedItems() == [widget.find_label_item(label="car")]
    headers = [widget.item(0), widget.item(2)]
    assert [header.flags() for header in headers] == [Qt.ItemFlag.NoItemFlags] * 2
    assert [header.text() for header in headers] == ["", ""]
    assert widget.find_label_item(label="") is None


def test_edit_button_requests_the_settings_labels(
    *, qtbot: QtBot, widget: UniqueLabelQListWidget, edit_requests: list[None]
) -> None:
    header = widget.itemWidget(widget.item(0))
    button = header.findChild(QtWidgets.QToolButton)
    assert button is not None

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert edit_requests == [None]


def test_set_settings_labels_moves_labels_between_sections(
    *, widget: UniqueLabelQListWidget
) -> None:
    for label in ["cat", "dog", "cow"]:
        widget.add_label_item(label=label, color=(255, 0, 0), from_settings=True)
    widget.add_label_item(label="car", color=(0, 0, 255))
    widget.setCurrentItem(_item(widget=widget, label="car"))

    widget.set_settings_labels(
        labels=["car", "cat", "bus"],
        found_in_annotations={"dog"},
        color=lambda _label: (0, 0, 0),
    )

    assert _rows(widget=widget) == [None, "car", "cat", "bus", None, "dog"]
    assert widget.selectedItems() == [widget.find_label_item(label="car")]


def test_set_settings_labels_keeps_a_selected_label_leaving_settings(
    *, widget: UniqueLabelQListWidget
) -> None:
    for label in ["cat", "dog"]:
        widget.add_label_item(label=label, color=(255, 0, 0), from_settings=True)
    widget.add_label_item(label="car", color=(0, 0, 255))
    widget.setCurrentItem(_item(widget=widget, label="cat"))

    widget.set_settings_labels(
        labels=["dog"], found_in_annotations={"cat"}, color=lambda _label: (0, 0, 0)
    )

    assert _rows(widget=widget) == [None, "dog", None, "car", "cat"]
    assert widget.selectedItems() == [_item(widget=widget, label="cat")]
    assert widget.currentItem() is _item(widget=widget, label="cat")


@pytest.mark.parametrize("key", [Qt.Key.Key_Delete, Qt.Key.Key_Backspace])
def test_removal_key_requests_only_found_labels(
    *, qtbot: QtBot, widget: UniqueLabelQListWidget, key: Qt.Key
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0), from_settings=True)
    widget.add_label_item(label="car", color=(0, 0, 255))
    widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
    _item(widget=widget, label="cat").setSelected(True)
    _item(widget=widget, label="car").setSelected(True)

    with qtbot.waitSignal(widget.label_remove_requested) as blocker:
        qtbot.keyClick(widget, key)

    assert blocker.args == ["car"]


def test_unused_labels_dim_with_the_current_palette(
    *, widget: UniqueLabelQListWidget
) -> None:
    widget.add_label_item(label="cat", color=(255, 0, 0), from_settings=True)
    widget.add_label_item(label="car", color=(0, 0, 255))
    widget.add_label_item(label="bus", color=(0, 255, 0))
    widget.set_unused_labels(labels={"cat", "car"})
    palette = widget.palette()
    palette.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor(1, 2, 3))
    widget.setPalette(palette)

    def text_color(label: str) -> QtGui.QColor:
        option = QtWidgets.QStyleOptionViewItem()
        option.initFrom(widget)
        index = widget.indexFromItem(_item(widget=widget, label=label))
        delegate = widget.itemDelegate()
        assert isinstance(delegate, QtWidgets.QStyledItemDelegate)
        delegate.initStyleOption(option, index)
        return option.palette.color(QtGui.QPalette.ColorRole.Text)

    assert text_color("car") == QtGui.QColor(1, 2, 3)
    assert text_color("cat") != QtGui.QColor(1, 2, 3)  # The label set never dims
    assert text_color("bus") != QtGui.QColor(1, 2, 3)


def test_label_moved_into_settings_stops_dimming(
    *, widget: UniqueLabelQListWidget
) -> None:
    widget.add_label_item(label="car", color=(0, 0, 255))
    widget.set_unused_labels(labels={"car"})

    widget.set_settings_labels(
        labels=["car"], found_in_annotations=set(), color=lambda _label: (0, 0, 0)
    )
    widget.set_unused_labels(labels=set())

    assert not _item(widget=widget, label="car").data(_UNUSED_ROLE)


def test_remove_label_items_selects_no_neighbor(
    *, widget: UniqueLabelQListWidget
) -> None:
    for label in ("car", "bus", "van"):
        widget.add_label_item(label=label, color=(0, 0, 255))
    widget.setCurrentItem(_item(widget=widget, label="bus"))
    widget.clearSelection()

    widget.remove_label_items(labels=["bus"])

    assert widget.labels() == ["car", "van"]
    assert widget.selectedItems() == []
