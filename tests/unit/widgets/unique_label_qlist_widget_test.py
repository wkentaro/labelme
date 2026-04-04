from __future__ import annotations

import pytest
from PyQt5.QtCore import Qt

from labelme.widgets.unique_label_qlist_widget import UniqueLabelQListWidget


@pytest.mark.gui
def test_find_label_item_returns_item(qtbot):
    """find_label_item() returns the QListWidgetItem for a known label."""
    widget = UniqueLabelQListWidget()
    qtbot.addWidget(widget)

    widget.add_label_item("cat", (255, 0, 0))
    widget.add_label_item("dog", (0, 255, 0))

    item = widget.find_label_item("cat")
    assert item is not None
    assert item.data(Qt.UserRole) == "cat"


@pytest.mark.gui
def test_find_label_item_returns_none_for_unknown(qtbot):
    """find_label_item() returns None when label is not in list."""
    widget = UniqueLabelQListWidget()
    qtbot.addWidget(widget)

    widget.add_label_item("cat", (255, 0, 0))

    item = widget.find_label_item("nonexistent")
    assert item is None


@pytest.mark.gui
def test_add_label_item_raises_on_duplicate(qtbot):
    """add_label_item() raises ValueError if label already exists."""
    widget = UniqueLabelQListWidget()
    qtbot.addWidget(widget)

    widget.add_label_item("cat", (255, 0, 0))

    with pytest.raises(ValueError, match="cat"):
        widget.add_label_item("cat", (0, 0, 255))


@pytest.mark.gui
def test_add_label_item_sets_colored_text(qtbot):
    """add_label_item() sets HTML text with color bullet."""
    widget = UniqueLabelQListWidget()
    qtbot.addWidget(widget)

    widget.add_label_item("person", (255, 0, 0))

    assert widget.count() == 1
    item = widget.item(0)
    assert item is not None
    # Text should contain the label name and an HTML color bullet
    text = item.text()
    assert "person" in text
    assert "ff0000" in text  # red color hex
    assert "●" in text


@pytest.mark.gui
def test_escape_key_clears_selection(qtbot):
    """Pressing Escape when an item is selected clears the selection."""
    widget = UniqueLabelQListWidget()
    qtbot.addWidget(widget)

    widget.add_label_item("cat", (255, 0, 0))
    widget.add_label_item("dog", (0, 255, 0))
    widget.show()
    qtbot.waitExposed(widget)

    # Select the first item
    widget.setCurrentRow(0)
    assert len(widget.selectedItems()) == 1

    # Press Escape — should clear selection
    qtbot.keyPress(widget, Qt.Key_Escape)
    assert widget.selectedItems() == []
