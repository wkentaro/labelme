from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import ANNOTATION_FOLDERS_KEY
from labelme._app import MainWindow

from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def _choose_folder(*, monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(folder),
    )


@pytest.mark.gui
def test_annotation_folder_is_restored_for_opened_folder(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    images = data_path / "raw"
    annotation_folder = tmp_path / "annotations"
    annotation_folder.mkdir()
    _choose_folder(monkeypatch=monkeypatch, folder=annotation_folder)

    first = main_win(file_or_dir=images)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=first)
    first.prompt_output_dir()
    assert first._output_dir == annotation_folder
    first.close()

    reopened = main_win(file_or_dir=images)
    assert reopened._output_dir == annotation_folder
    reopened.close()

    # Opening an image opens its folder, so the same entry applies.
    image = main_win(file_or_dir=images / "2011_000003.jpg")
    assert image._output_dir == annotation_folder

    # A folder without an entry keeps annotation files next to its images.
    image._load_from_file_or_dir(file_or_dir=str(data_path / "annotated"))
    assert image._output_dir is None


@pytest.mark.gui
def test_cli_output_wins_and_is_remembered(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
) -> None:
    images = data_path / "raw"
    remembered = tmp_path / "remembered"
    remembered.mkdir()
    cli = tmp_path / "cli"
    cli.mkdir()

    first = main_win(file_or_dir=images)
    first._window_state.setValue(ANNOTATION_FOLDERS_KEY, {str(images): str(remembered)})
    first.close()

    win = main_win(file_or_dir=images, output_dir=cli)
    assert win._output_dir == cli
    win.close()

    reopened = main_win(file_or_dir=images)
    assert reopened._output_dir == cli


@pytest.mark.gui
def test_cli_output_that_does_not_exist_yet_is_used(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
) -> None:
    cli = tmp_path / "new" / "annotations"

    win = main_win(file_or_dir=data_path / "raw", output_dir=cli)
    assert win._output_dir == cli
    assert cli.is_dir()


@pytest.mark.gui
def test_missing_annotation_folder_falls_back_next_to_images(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
) -> None:
    images = data_path / "raw"
    missing = tmp_path / "unmounted"

    first = main_win()
    first._window_state.setValue(ANNOTATION_FOLDERS_KEY, {str(images): str(missing)})
    first.close()

    win = main_win(file_or_dir=images)
    assert win._output_dir is None
    assert win.statusBar().currentMessage() == f"Annotation Folder not found: {missing}"
    # The entry stays so the folder is used again once it is back.
    assert win._window_state.value(ANNOTATION_FOLDERS_KEY) == {
        str(images): str(missing)
    }


@pytest.mark.gui
def test_annotation_folder_menu_needs_an_opened_folder(
    *,
    main_win: MainWinFactory,
    data_path: Path,
) -> None:
    win = main_win()
    change = win._actions.change_output_dir
    footer = win._docks.annotation_folder_footer
    assert not change.isEnabled()
    assert not footer.isVisibleTo(win)

    win._load_from_file_or_dir(file_or_dir=str(data_path / "raw"))
    assert change.isEnabled()
    assert footer.isVisibleTo(win)

    # An opened annotation file has no folder to remember the choice for.
    label_file = next((data_path / "annotated").glob("*.json"))
    win._load_from_file_or_dir(file_or_dir=str(label_file))
    assert not change.isEnabled()
    assert not footer.isVisibleTo(win)


@pytest.mark.gui
def test_cli_output_stays_with_its_folder(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
) -> None:
    cli = tmp_path / "cli"
    cli.mkdir()

    win = main_win(file_or_dir=data_path / "raw", output_dir=cli)
    assert win._output_dir == cli

    # Another folder opened in the same session uses its own entry.
    win._load_from_file_or_dir(file_or_dir=str(data_path / "annotated"))
    assert win._output_dir is None
    assert str(data_path / "annotated") not in win._remembered_output_dirs()


@pytest.mark.gui
def test_failed_folder_open_keeps_each_image_on_its_own_annotation_folder(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    critical_messages: list[str],
) -> None:
    first_images = data_path / "raw"
    first_folder = tmp_path / "first-annotations"
    first_folder.mkdir()
    second_images = tmp_path / "second"
    second_images.mkdir()
    (second_images / "01-broken.jpg").write_bytes(b"not an image")
    shutil.copyfile(
        src=first_images / "2011_000006.jpg", dst=second_images / "02-valid.jpg"
    )
    second_folder = tmp_path / "second-annotations"
    second_folder.mkdir()

    win = main_win()
    win._window_state.setValue(
        ANNOTATION_FOLDERS_KEY,
        {str(first_images): str(first_folder), str(second_images): str(second_folder)},
    )
    win._load_from_file_or_dir(file_or_dir=str(first_images))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    first_image = win._image_path
    assert first_image is not None

    # The second folder's first image fails, so the first image stays open
    # while the second folder's Images are listed.
    win._load_from_file_or_dir(file_or_dir=str(second_images))
    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._image_path == first_image
    assert win.current_label_file_path() == str(
        first_folder / f"{Path(first_image).stem}.json"
    )
    assert win._output_dir == second_folder

    win._load_from_file_or_dir(file_or_dir=str(second_images / "02-valid.jpg"))
    assert win.current_label_file_path() == str(second_folder / "02-valid.json")


@pytest.mark.gui
def test_failed_parent_folder_open_keeps_open_subfolder_image_destination(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    critical_messages: list[str],
) -> None:
    parent = tmp_path / "parent"
    sub = parent / "sub"
    sub.mkdir(parents=True)
    (parent / "01-broken.jpg").write_bytes(b"not an image")
    image = sub / "02-valid.jpg"
    shutil.copyfile(src=data_path / "raw" / "2011_000006.jpg", dst=image)
    sub_folder = tmp_path / "sub-annotations"
    sub_folder.mkdir()
    parent_folder = tmp_path / "parent-annotations"
    parent_folder.mkdir()

    win = main_win()
    win._window_state.setValue(
        ANNOTATION_FOLDERS_KEY,
        {str(sub): str(sub_folder), str(parent): str(parent_folder)},
    )
    win._load_from_file_or_dir(file_or_dir=str(image))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    # The open image is also listed under the parent, but the parent's first
    # image fails, so the open image keeps its own destination.
    win._load_from_file_or_dir(file_or_dir=str(parent))
    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._image_path == str(image)
    assert win._output_dir == parent_folder
    assert win.current_label_file_path() == str(sub_folder / "02-valid.json")


@pytest.mark.gui
def test_unsaved_changes_save_before_the_annotation_folder_switches(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    images = data_path / "raw"
    other = tmp_path / "other"
    shutil.copytree(data_path / "raw", other)
    remembered = tmp_path / "remembered"
    remembered.mkdir()

    win = main_win(file_or_dir=images, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._window_state.setValue(ANNOTATION_FOLDERS_KEY, {str(other): str(remembered)})
    win.mark_dirty()

    choices = [
        QtWidgets.QMessageBox.StandardButton.Discard,
        QtWidgets.QMessageBox.StandardButton.Save,
    ]
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "question", lambda *_args, **_kwargs: choices.pop(0)
    )
    save_dirs: list[str] = []
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        lambda *_args, **kwargs: (save_dirs.append(kwargs["dir"]), ("", ""))[1],
    )

    _choose_folder(monkeypatch=monkeypatch, folder=other)
    win._open_dir_with_dialog()

    # Asked once; the Discard is not followed by a second prompt whose Save
    # would default into the new folder's Annotation Folder.
    assert len(choices) == 1
    assert not save_dirs
    assert win._output_dir == remembered


def _footer_text(win: MainWindow, /) -> str:
    labels = win._docks.annotation_folder_footer.findChildren(QtWidgets.QLabel)
    return " ".join(label.text() for label in labels if label.text())


def _menu_action(win: MainWindow, text: str, /) -> QtGui.QAction:
    menu = win._docks.annotation_folder_footer.findChild(QtWidgets.QMenu)
    assert menu is not None
    for action in menu.actions():
        if action.text() == text:
            return action
    raise AssertionError(text)


def _check_states(win: MainWindow, /) -> list[Qt.CheckState]:
    file_list = win._docks.file_list
    return [file_list.item(i).checkState() for i in range(file_list.count())]


@pytest.mark.gui
def test_annotation_folder_footer_follows_changes(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    images = data_path / "annotated"
    annotation_folder = tmp_path / "annotations"
    annotation_folder.mkdir()
    _choose_folder(monkeypatch=monkeypatch, folder=annotation_folder)

    win = main_win(file_or_dir=images)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert _footer_text(win) == "Next to images"
    assert set(_check_states(win)) == {Qt.CheckState.Checked}

    _menu_action(win, "Choose Annotation Folder…").trigger()
    assert win._output_dir == annotation_folder
    assert _footer_text(win) == "annotations"
    assert set(_check_states(win)) == {Qt.CheckState.Unchecked}

    _menu_action(win, "Next to Images").trigger()
    assert win._output_dir is None
    assert _footer_text(win) == "Next to images"
    assert set(_check_states(win)) == {Qt.CheckState.Checked}
    assert win._window_state.value(ANNOTATION_FOLDERS_KEY) == {}


@pytest.mark.gui
def test_next_to_images_keeps_annotation_folder_when_unsaved_changes_are_kept(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=data_path / "raw", output_dir=tmp_path)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    monkeypatch.setattr(win, "_can_continue", lambda: False)

    _menu_action(win, "Next to Images").trigger()

    assert win._output_dir == tmp_path
    assert not _menu_action(win, "Next to Images").isChecked()


@pytest.mark.gui
def test_missing_annotation_folder_warns_in_footer_until_changed(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
) -> None:
    images = data_path / "raw"
    missing = tmp_path / "unmounted"

    win = main_win()
    win._window_state.setValue(ANNOTATION_FOLDERS_KEY, {str(images): str(missing)})
    win._load_from_file_or_dir(file_or_dir=str(images))
    assert _footer_text(win) == "Not found: unmounted · next to images"
    assert win._docks.annotation_folder_footer.toolTip() == str(missing)

    # Opening another folder replaces the warning.
    win._load_from_file_or_dir(file_or_dir=str(data_path / "annotated"))
    assert _footer_text(win) == "Next to images"


@pytest.mark.gui
def test_missing_folder_warning_survives_a_refused_folder(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    critical_messages: list[str],
) -> None:
    images = data_path / "raw"
    missing = tmp_path / "unmounted"
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "2011_000003.json").write_text("not json")
    _choose_folder(monkeypatch=monkeypatch, folder=broken)

    win = main_win()
    win._window_state.setValue(ANNOTATION_FOLDERS_KEY, {str(images): str(missing)})
    win._load_from_file_or_dir(file_or_dir=str(images))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    _menu_action(win, "Choose Annotation Folder…").trigger()

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert win._output_dir is None
    assert _footer_text(win) == "Not found: unmounted · next to images"


@pytest.mark.gui
def test_missing_folder_warning_survives_a_failed_open(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    critical_messages: list[str],
) -> None:
    images = data_path / "raw"
    missing = tmp_path / "unmounted"
    corrupt = tmp_path / "other" / "corrupt.jpg"
    corrupt.parent.mkdir()
    corrupt.write_bytes(b"not an image")

    win = main_win()
    win._window_state.setValue(ANNOTATION_FOLDERS_KEY, {str(images): str(missing)})
    win._load_from_file_or_dir(file_or_dir=str(images))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    win._load_from_file_or_dir(file_or_dir=str(corrupt))

    qtbot.waitUntil(lambda: len(critical_messages) == 1)
    assert _footer_text(win) == "Not found: unmounted · next to images"
