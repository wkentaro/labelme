from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDragEnterEvent
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def _make_drop_mime(*, paths: list[Path]) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def _drag_enter_accepted(*, win: MainWindow, mime: QMimeData) -> bool:
    event = QDragEnterEvent(
        QPoint(0, 0),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(win, event)
    return event.isAccepted()


def _send_drop(*, win: MainWindow, mime: QMimeData) -> None:
    event = QDropEvent(
        QPointF(0, 0),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(win, event)


@pytest.mark.gui
def test_drop_image_files_loads_them(
    *,
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win()
    win.show()
    qtbot.waitUntil(win.isVisible)

    first_image = data_path / "raw/2011_000003.jpg"
    second_image = data_path / "raw/2011_000006.jpg"

    mime = _make_drop_mime(paths=[first_image, second_image])
    assert _drag_enter_accepted(win=win, mime=mime)
    _send_drop(win=win, mime=mime)

    def check_image_list_populated() -> None:
        assert len(win.image_list) == 2
        assert str(first_image) in win.image_list
        assert str(second_image) in win.image_list

    qtbot.waitUntil(check_image_list_populated)
    assert first_image.name in win.windowTitle()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_dropped_image_files_respect_active_search_filter(
    *,
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(config_overrides={"file_search": r"000003\.jpg$"})
    win.show()
    qtbot.waitUntil(win.isVisible)

    matching_image = data_path / "raw/2011_000003.jpg"
    hidden_image = data_path / "raw/2011_000006.jpg"
    mime = _make_drop_mime(paths=[matching_image, hidden_image])

    assert _drag_enter_accepted(win=win, mime=mime)
    _send_drop(win=win, mime=mime)

    assert win.image_list == [str(matching_image)]
    assert matching_image.name in win.windowTitle()

    win._docks.file_search.setText(r"000006\.jpg$")
    assert win.image_list == [str(hidden_image)]

    win._docks.file_search.clear()
    assert win.image_list == [str(matching_image), str(hidden_image)]

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_opening_annotation_file_clears_loaded_directory_images(
    *,
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    pause: bool,
) -> None:
    annotated_dir = data_path / "annotated"
    win = main_win(file_or_dir=annotated_dir)
    win.show()
    qtbot.waitUntil(win.isVisible)

    image_path = annotated_dir / "2011_000003.jpg"
    win._load_from_file_or_dir(file_or_dir=str(annotated_dir / "2011_000003.json"))
    assert win.image_list == []

    mime = _make_drop_mime(paths=[image_path])
    assert _drag_enter_accepted(win=win, mime=mime)
    _send_drop(win=win, mime=mime)

    assert win.image_list == [str(image_path)]
    assert image_path.name in win.windowTitle()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_drag_enter_rejects_non_image_and_keeps_state(
    *,
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    original_title = raw_win.windowTitle()
    original_image_list = list(raw_win.image_list)

    non_image_file = tmp_path / "notes.txt"
    non_image_file.write_text("not an image")
    directory = data_path / "raw"

    for path in [directory, non_image_file]:
        mime = _make_drop_mime(paths=[path])
        assert not _drag_enter_accepted(win=raw_win, mime=mime)

    assert raw_win.windowTitle() == original_title
    assert list(raw_win.image_list) == original_image_list

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


def _open_dirty(*, main_win: MainWinFactory, qtbot: QtBot, image: Path) -> MainWindow:
    win = main_win(file_or_dir=image, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win.mark_dirty()
    return win


def _count_unsaved_prompts(
    *,
    monkeypatch: pytest.MonkeyPatch,
    answer: QMessageBox.StandardButton,
) -> list[QMessageBox.StandardButton]:
    asked: list[QMessageBox.StandardButton] = []

    def question(*_args: object, **_kwargs: object) -> QMessageBox.StandardButton:
        asked.append(answer)
        return answer

    monkeypatch.setattr(QMessageBox, "question", question)
    return asked


@pytest.mark.gui
def test_drop_with_unsaved_changes_asks_once_on_discard(
    *,
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = _open_dirty(
        main_win=main_win, qtbot=qtbot, image=data_path / "raw/2011_000003.jpg"
    )
    asked = _count_unsaved_prompts(
        monkeypatch=monkeypatch, answer=QMessageBox.StandardButton.Discard
    )
    dropped = data_path / "annotated/2011_000006.jpg"

    mime = _make_drop_mime(paths=[dropped])
    assert _drag_enter_accepted(win=win, mime=mime)
    _send_drop(win=win, mime=mime)

    assert len(asked) == 1
    assert dropped.name in win.windowTitle()


@pytest.mark.gui
def test_drop_with_unsaved_changes_adds_nothing_on_cancel(
    *,
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened = data_path / "raw/2011_000003.jpg"
    win = _open_dirty(main_win=main_win, qtbot=qtbot, image=opened)
    asked = _count_unsaved_prompts(
        monkeypatch=monkeypatch, answer=QMessageBox.StandardButton.Cancel
    )
    image_list = list(win.image_list)

    mime = _make_drop_mime(paths=[data_path / "annotated/2011_000006.jpg"])
    assert _drag_enter_accepted(win=win, mime=mime)
    _send_drop(win=win, mime=mime)

    assert len(asked) == 1
    assert win.image_list == image_list
    assert win._is_changed
    win.mark_clean()


@pytest.mark.gui
def test_drop_of_an_already_listed_image_does_not_ask(
    *,
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened = data_path / "raw/2011_000003.jpg"
    win = _open_dirty(main_win=main_win, qtbot=qtbot, image=opened)
    asked = _count_unsaved_prompts(
        monkeypatch=monkeypatch, answer=QMessageBox.StandardButton.Cancel
    )

    mime = _make_drop_mime(paths=[opened])
    assert _drag_enter_accepted(win=win, mime=mime)
    _send_drop(win=win, mime=mime)

    assert asked == []
    assert win._is_changed
    win.mark_clean()
