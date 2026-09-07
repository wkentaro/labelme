from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets.label_dialog import LabelDialog


@pytest.mark.parametrize(
    "modifier",
    [
        QtCore.Qt.KeyboardModifier.NoModifier,
        QtCore.Qt.KeyboardModifier.ShiftModifier,
        QtCore.Qt.KeyboardModifier.ControlModifier,
        QtCore.Qt.KeyboardModifier.AltModifier,
        QtCore.Qt.KeyboardModifier.MetaModifier,
    ],
)
def test_editor_arrows_match_native_single_selection(
    *, qtbot: QtBot, modifier: QtCore.Qt.KeyboardModifier
) -> None:
    dialog = LabelDialog(labels=["cat", "dog", "person"])
    qtbot.addWidget(dialog)
    reference = QtWidgets.QListWidget()
    qtbot.addWidget(reference)
    reference.addItems(["cat", "dog", "person"])
    with qtbot.waitActive(dialog):
        dialog.show()
        dialog.activateWindow()
    reference.setCurrentRow(1)
    dialog.label_list.setCurrentRow(1)
    dialog.edit.setFocus()
    expected_text = ["dog"]

    def remember_selection() -> None:
        item = reference.currentItem()
        if item is not None and item.isSelected():
            expected_text.append(item.text())

    reference.itemSelectionChanged.connect(remember_selection)

    for key in [QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Up]:
        qtbot.keyClick(reference, key, modifier)
        qtbot.keyClick(dialog.edit, key, modifier)
        assert dialog.label_list.currentRow() == reference.currentRow()
        assert [i.text() for i in dialog.label_list.selectedItems()] == [
            i.text() for i in reference.selectedItems()
        ]
        assert dialog.edit.text() == expected_text[-1]
        assert dialog.focusWidget() is dialog.edit


@pytest.mark.parametrize(
    ("labels", "row", "selected", "key", "expected_row", "expected_text"),
    [
        ([], -1, False, QtCore.Qt.Key.Key_Up, -1, "cat"),
        ([], -1, False, QtCore.Qt.Key.Key_Down, -1, "cat"),
        (["Cat"], -1, False, QtCore.Qt.Key.Key_Up, 0, "Cat"),
        (["Cat"], 0, True, QtCore.Qt.Key.Key_Down, 0, "cat"),
        (["Cat"], 0, False, QtCore.Qt.Key.Key_Up, 0, "cat"),
        (["Cat", "dog"], 0, False, QtCore.Qt.Key.Key_Down, 1, "dog"),
    ],
)
def test_arrows_preserve_text_without_a_new_selection(
    *,
    qtbot: QtBot,
    labels: list[str],
    row: int,
    selected: bool,
    key: QtCore.Qt.Key,
    expected_row: int,
    expected_text: str,
) -> None:
    dialog = LabelDialog(labels=labels)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.label_list.setCurrentRow(row)
    if not selected:
        dialog.label_list.clearSelection()
    dialog.edit.setText("cat")
    qtbot.keyClick(dialog.edit, key)
    assert dialog.label_list.currentRow() == expected_row
    assert dialog.edit.text() == expected_text
    if row == expected_row:
        assert bool(dialog.label_list.selectedItems()) == selected


def test_repeated_arrows_follow_reordered_rows(*, qtbot: QtBot) -> None:
    dialog = LabelDialog(labels=["cat", "dog", "person"], sort_labels=False)
    qtbot.addWidget(dialog)
    dialog.label_list.insertItem(0, dialog.label_list.takeItem(2))
    dialog.label_list.setCurrentRow(0)
    for expected in ["cat", "dog", "dog"]:
        event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_Down,
            QtCore.Qt.KeyboardModifier.NoModifier,
            autorep=True,
        )
        QtWidgets.QApplication.sendEvent(dialog.edit, event)
        assert dialog.edit.text() == expected


@pytest.mark.parametrize("completion", ["startswith", "contains"])
def test_completion_arrows_then_return_in_real_popup(
    *, qtbot: QtBot, completion: str
) -> None:
    dialog = LabelDialog(labels=["cat", "cattle", "dog"], completion=completion)
    qtbot.addWidget(dialog)

    def choose() -> None:
        dialog.edit.clear()
        qtbot.keyClicks(dialog.edit, "ca")
        completer = dialog.edit.completer()
        assert completer is not None
        popup = completer.popup()
        target = popup if completion == "contains" else dialog.edit
        assert target is not None
        if completion == "contains":
            assert target.isVisible()
        qtbot.keyClick(target, QtCore.Qt.Key.Key_Down)
        assert dialog.edit.text() == "cat"
        assert dialog.label_list.currentRow() == (-1 if completion == "contains" else 0)
        qtbot.keyClick(target, QtCore.Qt.Key.Key_Return)
        if completion == "contains":
            assert dialog.isVisible()
            qtbot.keyClick(dialog.edit, QtCore.Qt.Key.Key_Return)

    timer = QtCore.QTimer(dialog)
    timer.setSingleShot(True)
    timer.timeout.connect(dialog.reject)
    timer.start(3000)
    QtCore.QTimer.singleShot(0, choose)
    entry = dialog.popup(text="unknown", move=False)
    timer.stop()
    assert entry is not None
    assert entry.label == "cat"
