from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets._unique_label_qlist_widget import UniqueLabelQListWidget


@pytest.mark.gui
def test_unique_label_list_context_menu_on_unused_item(
    *,
    annotated_win: MainWindow,
) -> None:
    win = annotated_win
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    win._label_dialog.add_label_history(label="unused_fruit")
    unique_list.add_label_item(label="unused_fruit", color=(100, 100, 100))

    item = unique_list.find_label_item(label="unused_fruit")
    assert item is not None
    item_rect = unique_list.visualItemRect(item)
    point = item_rect.center()

    menu = win._build_unique_label_list_menu(point)
    actions = {action.text(): action for action in menu.actions()}

    assert "Remove from Label List" in actions
    remove_action = actions["Remove from Label List"]
    assert remove_action.isEnabled()

    assert "Clear Unused Labels" in actions
    clear_action = actions["Clear Unused Labels"]
    assert clear_action.isEnabled()


@pytest.mark.gui
def test_unique_label_list_context_menu_on_in_use_item(
    *,
    annotated_win: MainWindow,
) -> None:
    win = annotated_win
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    item = unique_list.find_label_item(label="amber_kite")
    assert item is not None
    item_rect = unique_list.visualItemRect(item)
    point = item_rect.center()

    menu = win._build_unique_label_list_menu(point)
    actions = {action.text(): action for action in menu.actions()}

    assert "Remove from Label List" in actions
    remove_action = actions["Remove from Label List"]
    assert not remove_action.isEnabled()


@pytest.mark.gui
def test_unique_label_list_context_menu_on_empty_area(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
) -> None:
    win = annotated_win
    win.resize(1000, 1000)
    qtbot.wait(50)
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    last_item = unique_list.item(unique_list.count() - 1)
    assert last_item is not None
    last_rect = unique_list.visualItemRect(last_item)
    empty_pos = QtCore.QPoint(last_rect.center().x(), last_rect.bottom() + 30)
    assert unique_list.itemAt(empty_pos) is None

    menu = win._build_unique_label_list_menu(empty_pos)
    action_texts = [action.text() for action in menu.actions()]

    assert "Remove from Label List" not in action_texts
    assert "Clear Unused Labels" in action_texts


@pytest.mark.gui
def test_remove_unused_label_action_removes_from_dock_and_dialog(
    *,
    annotated_win: MainWindow,
) -> None:
    win = annotated_win
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    win._label_dialog.add_label_history(label="obsolete_label")
    unique_list.add_label_item(label="obsolete_label", color=(50, 50, 50))
    assert "obsolete_label" in unique_list.labels
    assert "obsolete_label" in win._label_dialog.label_history

    item = unique_list.find_label_item(label="obsolete_label")
    assert item is not None
    point = unique_list.visualItemRect(item).center()

    menu = win._build_unique_label_list_menu(point)
    actions = {action.text(): action for action in menu.actions()}
    actions["Remove from Label List"].trigger()

    assert "obsolete_label" not in unique_list.labels
    assert "obsolete_label" not in win._label_dialog.label_history


@pytest.mark.gui
def test_delete_key_on_unique_label_list_removes_unused_label(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
) -> None:
    win = annotated_win
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    win._label_dialog.add_label_history(label="extra_tag")
    unique_list.add_label_item(label="extra_tag", color=(10, 20, 30))

    item = unique_list.find_label_item(label="extra_tag")
    assert item is not None
    unique_list.setCurrentItem(item)

    qtbot.keyClick(unique_list, Qt.Key.Key_Delete)

    assert "extra_tag" not in unique_list.labels
    assert "extra_tag" not in win._label_dialog.label_history


@pytest.mark.gui
def test_delete_key_on_unique_label_list_in_use_shows_error(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = annotated_win
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    item = unique_list.find_label_item(label="amber_kite")
    assert item is not None
    unique_list.setCurrentItem(item)

    error_shown: list[str] = []
    monkeypatch.setattr(
        win,
        "show_error_message",
        lambda *, title, message: error_shown.append(f"{title}: {message}") or 0,
    )

    qtbot.keyClick(unique_list, Qt.Key.Key_Delete)

    assert len(error_shown) == 1
    assert "Cannot Remove Label" in error_shown[0]
    assert "amber_kite" in unique_list.labels


@pytest.mark.gui
def test_clear_unused_labels_clears_only_unused_labels(
    *,
    annotated_win: MainWindow,
) -> None:
    win = annotated_win
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    win._config["labels"] = ["predefined_unused"]
    unique_list.add_label_item(label="predefined_unused", color=(1, 2, 3))

    win._label_dialog.add_label_history(label="legacy_1")
    unique_list.add_label_item(label="legacy_1", color=(4, 5, 6))
    win._label_dialog.add_label_history(label="legacy_2")
    unique_list.add_label_item(label="legacy_2", color=(7, 8, 9))

    assert "legacy_1" in unique_list.labels
    assert "legacy_2" in unique_list.labels
    assert "predefined_unused" in unique_list.labels

    win._clear_unused_unique_labels()

    # Predefined label and canvas active labels must be kept
    assert "predefined_unused" in unique_list.labels
    assert "amber_kite" in unique_list.labels
    # Unused labels must be gone
    assert "legacy_1" not in unique_list.labels
    assert "legacy_2" not in unique_list.labels
    assert "legacy_1" not in win._label_dialog.label_history
    assert "legacy_2" not in win._label_dialog.label_history

    # When no unused labels remain, Clear Unused Labels action is disabled
    menu = win._build_unique_label_list_menu(QtCore.QPoint(0, 0))
    actions = {action.text(): action for action in menu.actions()}
    assert not actions["Clear Unused Labels"].isEnabled()


@pytest.mark.gui
def test_show_unique_label_list_menu_executes_popup(
    *,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = annotated_win
    menu_exec_called: list[int] = []
    dummy_menu = QtWidgets.QMenu(win)
    monkeypatch.setattr(
        dummy_menu,
        "exec",
        lambda *_args, **_kwargs: menu_exec_called.append(1) or None,
    )
    monkeypatch.setattr(win, "_build_unique_label_list_menu", lambda _p: dummy_menu)
    win.show_unique_label_list_menu(QtCore.QPoint(10, 10))
    assert menu_exec_called == [1]
