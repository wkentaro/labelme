from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets._unique_label_qlist_widget import _UNUSED_ROLE
from labelme._widgets._unique_label_qlist_widget import UniqueLabelQListWidget


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

    menu = win._build_unique_label_list_menu(point=point)
    actions = {action.text(): action for action in menu.actions()}

    assert "Remove from Label List" in actions
    remove_action = actions["Remove from Label List"]
    assert not remove_action.isEnabled()


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

    menu = win._build_unique_label_list_menu(point=empty_pos)
    action_texts = [action.text() for action in menu.actions()]

    assert "Remove from Label List" not in action_texts
    assert "Clear Unused Labels" in action_texts


def test_remove_unused_label_action_removes_from_dock_and_dialog(
    *,
    annotated_win: MainWindow,
) -> None:
    win = annotated_win
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    win._label_dialog.add_label_history(label="obsolete_label")
    unique_list.add_label_item(label="obsolete_label", color=(50, 50, 50))

    item = unique_list.find_label_item(label="obsolete_label")
    assert item is not None
    point = unique_list.visualItemRect(item).center()

    menu = win._build_unique_label_list_menu(point=point)
    actions = {action.text(): action for action in menu.actions()}
    actions["Remove from Label List"].trigger()

    assert unique_list.find_label_item(label="obsolete_label") is None
    assert "obsolete_label" not in win._label_dialog.label_history


def test_delete_key_on_unique_label_list_removes_unused_label(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = annotated_win
    monkeypatch.setattr(win, "_can_continue", lambda: True)
    canvas = win._canvas_widgets.canvas
    shapes = tuple(canvas.shapes)
    canvas.select_shapes(shapes=[shapes[0]])
    assert win._actions.delete.isEnabled()
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    win._label_dialog.add_label_history(label="extra_tag")
    unique_list.add_label_item(label="extra_tag", color=(10, 20, 30))

    item = unique_list.find_label_item(label="extra_tag")
    assert item is not None
    unique_list.setCurrentItem(item)
    unique_list.setFocus()
    qtbot.waitUntil(unique_list.hasFocus)

    qtbot.keyClick(unique_list, Qt.Key.Key_Delete)

    assert tuple(canvas.shapes) == shapes
    assert unique_list.find_label_item(label="extra_tag") is None
    assert "extra_tag" not in win._label_dialog.label_history


@pytest.mark.parametrize("deselect", ["escape", "empty-click"])
def test_removal_key_ignores_unselected_label(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    deselect: str,
) -> None:
    win = annotated_win
    monkeypatch.setattr(win, "_can_continue", lambda: True)
    unique_list = win._docks.unique_label_list
    win._label_dialog.add_label_history(label="extra_tag")
    unique_list.add_label_item(label="extra_tag", color=(10, 20, 30))
    item = unique_list.find_label_item(label="extra_tag")
    assert item is not None
    unique_list.setCurrentItem(item)
    unique_list.setFocus()
    qtbot.waitUntil(unique_list.hasFocus)
    if deselect == "escape":
        qtbot.keyClick(unique_list, Qt.Key.Key_Escape)
    else:
        point = unique_list.viewport().rect().bottomLeft()
        assert unique_list.itemAt(point) is None
        qtbot.mouseClick(unique_list.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert not unique_list.selectedItems()
    assert unique_list.currentItem() is item
    canvas = win._canvas_widgets.canvas
    shapes = tuple(canvas.shapes)
    canvas.select_shapes(shapes=[shapes[0]])
    assert win._actions.delete.isEnabled()

    qtbot.keyClick(unique_list, Qt.Key.Key_Delete)

    assert tuple(canvas.shapes) == shapes
    assert unique_list.find_label_item(label="extra_tag") is not None
    assert "extra_tag" in win._label_dialog.label_history


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
    assert unique_list.find_label_item(label="amber_kite") is not None


def test_predefined_label_is_not_removable_from_the_label_list(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = annotated_win
    errors: list[dict[str, str]] = []
    monkeypatch.setattr(
        win, "show_error_message", lambda **kwargs: errors.append(kwargs)
    )
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    win._label_dialog.add_label_history(label="predefined_unused")
    unique_list.add_label_item(
        label="predefined_unused", color=(1, 2, 3), from_settings=True
    )
    item = unique_list.find_label_item(label="predefined_unused")
    assert item is not None

    menu = win._build_unique_label_list_menu(
        point=unique_list.visualItemRect(item).center()
    )
    assert "Remove from Label List" not in [a.text() for a in menu.actions()]

    unique_list.setCurrentItem(item)
    unique_list.setFocus()
    qtbot.waitUntil(unique_list.hasFocus)
    qtbot.keyClick(unique_list, Qt.Key.Key_Delete)

    assert errors == []
    assert unique_list.find_label_item(label="predefined_unused") is not None
    assert "predefined_unused" in win._label_dialog.label_history


def test_clear_unused_labels_refreshes_shape_colors_once(
    *, annotated_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = annotated_win
    for label in ("legacy_1", "legacy_2", "legacy_3"):
        win._label_dialog.add_label_history(label=label)
        win._docks.unique_label_list.add_label_item(label=label, color=(4, 5, 6))
    refreshes: list[None] = []
    monkeypatch.setattr(win, "_refresh_shape_colors", lambda: refreshes.append(None))

    win._clear_unused_unique_labels()

    assert len(refreshes) == 1


def test_clear_unused_labels_clears_only_unused_labels(
    *,
    annotated_win: MainWindow,
) -> None:
    win = annotated_win
    unique_list: UniqueLabelQListWidget = win._docks.unique_label_list
    unique_list.add_label_item(
        label="predefined_unused", color=(1, 2, 3), from_settings=True
    )

    win._label_dialog.add_label_history(label="legacy_1")
    unique_list.add_label_item(label="legacy_1", color=(4, 5, 6))
    win._label_dialog.add_label_history(label="legacy_2")
    unique_list.add_label_item(label="legacy_2", color=(7, 8, 9))

    win._clear_unused_unique_labels()

    # Predefined label and canvas active labels must be kept
    assert unique_list.find_label_item(label="predefined_unused") is not None
    assert unique_list.find_label_item(label="amber_kite") is not None
    # Unused labels must be gone
    assert unique_list.find_label_item(label="legacy_1") is None
    assert unique_list.find_label_item(label="legacy_2") is None
    assert "legacy_1" not in win._label_dialog.label_history
    assert "legacy_2" not in win._label_dialog.label_history

    # When no unused labels remain, Clear Unused Labels action is disabled
    menu = win._build_unique_label_list_menu(point=QtCore.QPoint(0, 0))
    actions = {action.text(): action for action in menu.actions()}
    assert not actions["Clear Unused Labels"].isEnabled()


def test_deleting_a_labels_last_shape_dims_it_for_clear_unused(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = annotated_win
    monkeypatch.setattr(win, "_can_continue", lambda: True)
    unique_list = win._docks.unique_label_list
    [clear_unused] = [
        button
        for button in unique_list.findChildren(QtWidgets.QToolButton)
        if button.text() == "Clear Unused"
    ]
    item = unique_list.find_label_item(label="amber_kite")
    assert item is not None
    qtbot.wait(10)  # let the load's deferred refresh run
    assert not item.data(_UNUSED_ROLE)
    assert not clear_unused.isEnabled()

    canvas = win._canvas_widgets.canvas
    canvas.select_shapes(
        shapes=[shape for shape in canvas.shapes if shape.label == "amber_kite"]
    )
    win.delete_selected_shapes()

    qtbot.waitUntil(clear_unused.isEnabled)
    assert item.data(_UNUSED_ROLE)

    qtbot.mouseClick(clear_unused, Qt.MouseButton.LeftButton)

    assert unique_list.find_label_item(label="amber_kite") is None
    assert "amber_kite" not in win._label_dialog.label_history
    assert not clear_unused.isEnabled()
    # The deletion auto-saves; closing the window mid-save fails teardown.
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)


def test_unique_label_list_menu_is_freed_after_closing(
    *, annotated_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_menu = annotated_win._build_unique_label_list_menu

    def build_closed_menu(*, point: QtCore.QPoint) -> QtWidgets.QMenu:
        menu = build_menu(point=point)
        monkeypatch.setattr(menu, "exec", lambda *_args: None)  # Closes at once.
        return menu

    monkeypatch.setattr(
        annotated_win, "_build_unique_label_list_menu", build_closed_menu
    )
    n_menus = len(annotated_win.findChildren(QtWidgets.QMenu))

    for _ in range(3):
        annotated_win.show_unique_label_list_menu(QtCore.QPoint(0, 0))
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

    assert len(annotated_win.findChildren(QtWidgets.QMenu)) == n_menus
