from __future__ import annotations

import re
from typing import Final

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory

_MNEMONIC_RE: Final = re.compile(r"&(\w)")


def _mnemonics(actions: list[QtGui.QAction], /) -> list[str]:
    letters: list[str] = []
    for act in actions:
        if act.isSeparator():
            continue
        match = _MNEMONIC_RE.search(act.text())
        if match:
            letters.append(match.group(1).upper())
    return letters


@pytest.mark.gui
@pytest.mark.parametrize("menu_name", ["file", "view", "edit", "help"])
def test_menu_mnemonics_are_unique_within_each_menu(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    menu_name: str,
    pause: bool,
) -> None:
    win = main_win()
    win.show()

    menu: QtWidgets.QMenu = getattr(win._menus, menu_name)
    letters = _mnemonics(menu.actions())

    assert len(letters) == len(set(letters)), (
        f"duplicate mnemonics in the {menu_name!r} menu: {letters}"
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_top_level_menu_mnemonics_are_unique(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    pause: bool,
) -> None:
    win = main_win()
    win.show()

    letters = _mnemonics(win.menuBar().actions())

    assert len(letters) == len(set(letters))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_menu_actions_do_not_expose_toolbar_line_breaks(
    *, main_win: MainWinFactory, qtbot: QtBot, pause: bool
) -> None:
    win = main_win()
    win.show()

    assert all(
        "\n" not in action.text()
        for menu in (win._menus.file, win._menus.edit, win._menus.view)
        for action in menu.actions()
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_primary_dock_controls_have_accessible_names(
    *, main_win: MainWinFactory, qtbot: QtBot, pause: bool
) -> None:
    win = main_win()
    win.show()

    assert {
        win._docks.flag_list.accessibleName(),
        win._docks.label_list.accessibleName(),
        win._docks.unique_label_list.accessibleName(),
        win._docks.file_search.accessibleName(),
        win._docks.file_list.accessibleName(),
    } == {"Flags", "Shape List", "Label List", "Search Filename", "File List"}

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_on_load_active_group_covers_draw_and_file_actions(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    pause: bool,
) -> None:
    win = main_win()
    win.show()
    actions = win._actions

    draw_actions = {draw_action for _, draw_action in actions.draw}
    assert draw_actions <= set(actions.on_load_active)
    assert actions.close in actions.on_load_active
    assert actions.brightness_contrast in actions.on_load_active
    assert actions.save_as in actions.on_load_active
    # Actions gated on shapes/selection/history rather than a loaded image
    # are enabled elsewhere and must stay out of this group.
    assert actions.save not in actions.on_load_active
    assert actions.delete not in actions.on_load_active

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_on_shapes_present_group_covers_visibility(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    pause: bool,
) -> None:
    win = main_win()
    win.show()
    actions = win._actions

    assert set(actions.on_shapes_present) == {
        actions.hide_all,
        actions.show_all,
        actions.toggle_all,
    }

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_canvas_context_menu_without_selection_matches_configured_actions(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    pause: bool,
) -> None:
    win = main_win()
    win.show()

    context_menu = win._canvas_widgets.canvas.context_menus.without_selection
    assert context_menu.actions() == list(win._actions.context_menu)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_canvas_context_menu_with_selection_leads_with_copy(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    pause: bool,
) -> None:
    win = main_win()
    win.show()

    with_selection = win._canvas_widgets.canvas.context_menus.with_selection.actions()

    assert len(with_selection) == 2
    first, second = with_selection
    assert first.text().replace("&", "") == "Copy Here"
    assert second.text().replace("&", "") == "Move Here"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
