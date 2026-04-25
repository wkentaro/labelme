from __future__ import annotations

import pytest
from PyQt5 import QtCore
from PyQt5 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme.widgets import LabelDialog
from labelme.widgets import LabelQLineEdit


@pytest.mark.gui
def test_LabelQLineEdit(qtbot: QtBot) -> None:
    list_widget = QtWidgets.QListWidget()
    list_widget.addItems(["cat", "dog", "person"])
    widget = LabelQLineEdit()
    widget.set_list_widget(list_widget)
    qtbot.addWidget(widget)

    # key press to navigate in label list
    item = widget.list_widget.findItems("cat", QtCore.Qt.MatchExactly)[0]
    widget.list_widget.setCurrentItem(item)
    current_item = widget.list_widget.currentItem()
    assert current_item is not None
    assert current_item.text() == "cat"
    qtbot.keyPress(widget, QtCore.Qt.Key_Down)
    current_item = widget.list_widget.currentItem()
    assert current_item is not None
    assert current_item.text() == "dog"

    # key press to enter label
    qtbot.keyPress(widget, QtCore.Qt.Key_P)
    qtbot.keyPress(widget, QtCore.Qt.Key_E)
    qtbot.keyPress(widget, QtCore.Qt.Key_R)
    qtbot.keyPress(widget, QtCore.Qt.Key_S)
    qtbot.keyPress(widget, QtCore.Qt.Key_O)
    qtbot.keyPress(widget, QtCore.Qt.Key_N)
    assert widget.text() == "person"


@pytest.mark.gui
def test_LabelDialog_add_label_history(qtbot: QtBot) -> None:
    labels = ["cat", "dog", "person"]
    widget = LabelDialog(labels=labels, sort_labels=True)
    qtbot.addWidget(widget)

    widget.add_label_history("bicycle")
    assert widget.label_list.count() == 4
    widget.add_label_history("bicycle")
    assert widget.label_list.count() == 4
    item: QtWidgets.QListWidgetItem | None = widget.label_list.item(0)
    assert item
    assert item.text() == "bicycle"


@pytest.mark.gui
def test_LabelDialog_popup(qtbot: QtBot) -> None:
    labels = ["cat", "dog", "person"]
    widget = LabelDialog(labels=labels, sort_labels=True)
    qtbot.addWidget(widget)

    # popup(text='cat')

    def interact() -> None:
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_P)  # enter 'p' for 'person'  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA

    QtCore.QTimer.singleShot(500, interact)
    label, flags, group_id, description = widget.popup("cat")
    assert label == "person"
    assert flags == {}
    assert group_id is None
    assert description == ""

    # popup()

    def interact() -> None:
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA

    QtCore.QTimer.singleShot(500, interact)
    label, flags, group_id, description = widget.popup()
    assert label == "person"
    assert flags == {}
    assert group_id is None
    assert description == ""

    # popup() + key_Up

    def interact() -> None:
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Up)  # 'person' -> 'dog'  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA
        qtbot.keyClick(widget.edit, QtCore.Qt.Key_Enter)  # NOQA

    QtCore.QTimer.singleShot(500, interact)
    label, flags, group_id, description = widget.popup()
    assert label == "dog"
    assert flags == {}
    assert group_id is None
    assert description == ""
