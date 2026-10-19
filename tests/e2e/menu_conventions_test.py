from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Final

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme._app import MainWindow

from .conftest import MainWinFactory

# Words that stay lowercase inside a title-case menu item (Apple HIG).
_MINOR_WORDS: Final = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)


def _english_window(main_win: MainWinFactory, /) -> MainWindow:
    # The rules and allowlists are about the source strings; a translated
    # session would fail them for reasons unrelated to the menus.
    return main_win(config_overrides={"language": "en_US"})


def _plain(text: str, /) -> str:
    return text.replace("&", "").replace("\n", " ").strip()


def _menus(win: MainWindow, /) -> Iterator[QtWidgets.QMenu]:
    # Every menu the window owns (menu bar, toolbar overflow, Annotation Folder
    # footer), plus the context menus that are created without a parent.
    yield from win.findChildren(QtWidgets.QMenu)
    yield win._menus.label_list
    yield win._canvas_widgets.canvas.context_menu


def _menu_actions(win: MainWindow, /) -> list[QtGui.QAction]:
    seen: dict[int, QtGui.QAction] = {}
    for menu in _menus(win):
        for action in menu.actions():
            # Widget actions (e.g. the polygon detail slider) have no text, and
            # submenu entries (the menu bar's overflow) are not commands.
            if (
                action.isSeparator()
                or isinstance(action, QtWidgets.QWidgetAction)
                or action.menu() is not None
            ):
                continue
            seen.setdefault(id(action), action)
    return list(seen.values())


def _is_title_case(text: str, /) -> bool:
    words = [w for w in re.split(r"[ /]", text.rstrip("…")) if w]
    for index, word in enumerate(words):
        if 0 < index < len(words) - 1 and word.lower() in _MINOR_WORDS:
            if word != word.lower():
                return False
        elif not word[0].isupper():
            return False
    return True


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Fit to Window", True),
        ("Select Shape to the Left", True),
        ("Save As…", True),
        ("Keep Previous Brightness/Contrast", True),
        ("Copy To Clipboard", False),
        ("Zoom in", False),
        ("Undo last point", False),
    ],
)
def test_is_title_case(*, text: str, expected: bool) -> None:
    assert _is_title_case(text) is expected


def _icon_key(action: QtGui.QAction, /) -> bytes:
    image = action.icon().pixmap(16, 16).toImage()
    return bytes(image.constBits())


@pytest.mark.gui
def test_menu_text_has_no_newline(*, main_win: MainWinFactory) -> None:
    # Known violations; the change that fixes one removes it, and a stale entry
    # fails, so the set only shrinks.
    allowed = frozenset(
        {
            "&Save\n",
            "Undo\n",
            "&Hide\nShapes",
            "&Show\nShapes",
            "&Toggle\nShapes",
        }
    )
    win = _english_window(main_win)
    found = {a.text() for a in _menu_actions(win) if "\n" in a.text()}
    assert found == allowed


@pytest.mark.gui
def test_menu_items_use_title_case(*, main_win: MainWinFactory) -> None:
    # Known violations; the change that fixes one removes it, and a stale entry
    # fails, so the set only shrinks.
    allowed = frozenset({"Undo last point"})
    win = _english_window(main_win)
    found = {
        _plain(a.text())
        for a in _menu_actions(win)
        if not _is_title_case(_plain(a.text()))
    }
    assert found == allowed


@pytest.mark.gui
def test_dialog_actions_end_with_ellipsis(*, main_win: MainWinFactory) -> None:
    # Actions that ask for more input before they act carry an ellipsis.
    dialog_actions = (
        "open",
        "open_dir",
        "save_as",
        "change_output_dir",
        "edit",
        "brightness_contrast",
    )
    # Known violations; the change that fixes one removes it, and a stale entry
    # fails, so the set only shrinks.
    allowed = frozenset({"save_as", "edit", "brightness_contrast"})
    win = _english_window(main_win)
    found = {
        name
        for name in dialog_actions
        if not _plain(getattr(win._actions, name).text()).endswith("…")
    }
    assert found == allowed


@pytest.mark.gui
def test_checkable_menu_items_have_no_icon(*, main_win: MainWinFactory) -> None:
    # Mode toggles that also sit on the toolbar keep their icon; other checkable
    # items rely on the checkmark alone.
    toggles_with_icon = frozenset({"fit_window", "fit_selection"})
    win = _english_window(main_win)
    allowed = {id(getattr(win._actions, name)) for name in toggles_with_icon}
    found = {
        _plain(a.text())
        for a in _menu_actions(win)
        if a.isCheckable() and not a.icon().isNull() and id(a) not in allowed
    }
    assert found == set()


@pytest.mark.gui
def test_each_icon_belongs_to_one_action(*, main_win: MainWinFactory) -> None:
    # Known violations; the change that fixes one removes it, and a stale entry
    # fails, so the set only shrinks.
    allowed = frozenset(
        {
            frozenset({"Undo", "Undo last point"}),
            frozenset({"Show Shapes", "Toggle Shapes"}),
        }
    )
    win = _english_window(main_win)
    by_icon: dict[bytes, set[str]] = {}
    for action in _menu_actions(win):
        if not action.icon().isNull():
            by_icon.setdefault(_icon_key(action), set()).add(_plain(action.text()))
    shared = {frozenset(texts) for texts in by_icon.values() if len(texts) > 1}
    assert shared == allowed


@pytest.mark.gui
def test_view_menu_ends_with_separator(*, main_win: MainWinFactory) -> None:
    # macOS appends Enter Full Screen to the View menu. Without a separator it
    # joins the last section, and its SF Symbol makes AppKit indent the
    # icon-less items there.
    win = _english_window(main_win)
    ends_with_separator = win._menus.view.actions()[-1].isSeparator()
    assert ends_with_separator


@pytest.mark.gui
def test_menu_commands_have_icon(*, main_win: MainWinFactory) -> None:
    # Known violations; the change that fixes one removes it, and a stale entry
    # fails, so the set only shrinks.
    allowed = frozenset({"Choose Annotation Folder…"})
    win = _english_window(main_win)
    found = {
        _plain(a.text())
        for a in _menu_actions(win)
        if not a.isCheckable() and a.icon().isNull()
    }
    assert found == allowed


@pytest.mark.gui
def test_menu_text_avoids_glossary_terms(*, main_win: MainWinFactory) -> None:
    # Terms GLOSSARY.md tells the UI to avoid.
    avoided_terms = ("label file", "output dir", "save dir", "file list")
    win = _english_window(main_win)
    texts = [
        text.lower()
        for a in _menu_actions(win)
        for text in (_plain(a.text()), a.toolTip())
    ]
    texts += [
        dock.windowTitle().lower() for dock in win.findChildren(QtWidgets.QDockWidget)
    ]
    found = {term for term in avoided_terms for text in texts if term in text}
    assert found == set()
