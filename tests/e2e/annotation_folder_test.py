from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import ANNOTATION_FOLDERS_KEY
from labelme._app import MainWindow
from labelme._shape import Shape

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
    footer = win._docks.annotation_folder_footer
    labels = footer.findChildren(QtWidgets.QLabel)
    return " ".join(
        label.text() for label in labels if label.isVisibleTo(footer) and label.text()
    )


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
    assert _footer_text(win) == "3 of 3 annotated · next to images"
    assert set(_check_states(win)) == {Qt.CheckState.Checked}

    _menu_action(win, "Change Annotation Folder…").trigger()
    assert win._output_dir == annotation_folder
    assert _footer_text(win) == "0 of 3 annotated in annotations"
    assert set(_check_states(win)) == {Qt.CheckState.Unchecked}

    _menu_action(win, "Next to Images").trigger()
    assert win._output_dir is None
    assert _footer_text(win) == "3 of 3 annotated · next to images"
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
    assert _footer_text(win) == "3 of 3 annotated · next to images"


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

    _menu_action(win, "Change Annotation Folder…").trigger()

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


@pytest.mark.gui
def test_footer_counts_annotated_images(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    win = main_win(file_or_dir=data_path / "raw", output_dir=out)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert _footer_text(win) == "0 of 3 annotated in out"

    monkeypatch.setattr(
        win, "prompt_save_file_path", lambda: str(out / "2011_000003.json")
    )
    win._save_label_file(save_as=False)
    qtbot.waitUntil(lambda: _footer_text(win) == "1 of 3 annotated in out")

    # Images hidden by the search box still count.
    win._docks.file_search.setText(r"000025")
    assert _footer_text(win) == "1 of 3 annotated in out"


@pytest.mark.gui
def test_footer_is_hidden_without_images(
    *, main_win: MainWinFactory, data_path: Path, tmp_path: Path
) -> None:
    win = main_win()
    footer = win._docks.annotation_folder_footer
    assert not footer.isVisibleTo(win)

    # Dropped images are listed without an opened folder to remember an
    # Annotation Folder for.
    win.import_dropped_image_files(
        image_files=[str(data_path / "raw" / "2011_000003.jpg")]
    )
    assert win.image_list
    assert not footer.isVisibleTo(win)

    empty = tmp_path / "empty"
    empty.mkdir()
    win._load_from_file_or_dir(file_or_dir=str(empty))
    assert not footer.isVisibleTo(win)


@pytest.mark.gui
def test_footer_counts_saves_and_deletes_of_a_hidden_image(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    win = main_win(file_or_dir=data_path / "raw", output_dir=out)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    # The open image is 2011_000003.jpg; hide it from the list.
    win._docks.file_search.setText(r"000025")
    assert _footer_text(win) == "0 of 3 annotated in out"

    monkeypatch.setattr(
        win, "prompt_save_file_path", lambda: str(out / "2011_000003.json")
    )
    win._save_label_file(save_as=False)
    qtbot.waitUntil(lambda: (out / "2011_000003.json").exists())
    assert _footer_text(win) == "1 of 3 annotated in out"

    monkeypatch.setattr(win, "_confirm_deletion", lambda **_kwargs: True)
    win.delete_file()
    assert not (out / "2011_000003.json").exists()
    assert _footer_text(win) == "0 of 3 annotated in out"


@pytest.mark.gui
def test_footer_recounts_once_per_save(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Images sharing a stem each have their own Annotation File in the
    # Annotation Folder, and a save of one re-checks every same-stem image.
    images = tmp_path / "images"
    for name in ("a", "b", "c"):
        (images / name).mkdir(parents=True)
        shutil.copy(data_path / "raw" / "2011_000003.jpg", images / name / "frame.jpg")
    out = tmp_path / "out"
    out.mkdir()
    win = main_win(file_or_dir=images, output_dir=out)
    footer = win._docks.annotation_folder_footer
    counts: list[tuple[int, int]] = []
    set_count = footer.set_count
    monkeypatch.setattr(
        footer,
        "set_count",
        lambda *, annotated, total: (
            counts.append((annotated, total)),
            set_count(annotated=annotated, total=total),
        ),
    )

    for name in ("a", "b", "c"):
        (out / name).mkdir(parents=True)
        (out / name / "frame.json").write_text("{}")
    win._refresh_image_list_checkmarks(label_path=str(out / "a" / "frame.json"))
    assert counts == [(3, 3)]


@pytest.mark.gui
def test_subfolder_images_with_same_name_have_unique_annotation_files(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> None:
    images = tmp_path / "images"
    (images / "a").mkdir(parents=True)
    (images / "b").mkdir(parents=True)
    shutil.copy(data_path / "raw" / "2011_000003.jpg", images / "a" / "0001.jpg")
    shutil.copy(data_path / "raw" / "2011_000003.jpg", images / "b" / "0001.jpg")

    out = tmp_path / "annotations"
    out.mkdir()

    win = main_win(file_or_dir=images, output_dir=out)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    # Initial state: 0 of 2 annotated in annotations, neither is checked
    assert _footer_text(win) == f"0 of 2 annotated in {out.name}"
    assert _check_states(win) == [Qt.CheckState.Unchecked, Qt.CheckState.Unchecked]

    # Draw shape on a/0001.jpg (row 0) and save
    win._commit_shapes(
        [Shape(label="box_a", points=np.array([[10.0, 10.0], [50.0, 50.0]]))]
    )
    win.save_labels(label_path=win.current_label_file_path())
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)

    # Only a/0001.json is created under annotations/a/
    assert (out / "a" / "0001.json").exists()
    assert not (out / "b" / "0001.json").exists()
    assert not (out / "0001.json").exists()

    # Footer and checkmarks show 1 of 2 annotated
    assert _footer_text(win) == f"1 of 2 annotated in {out.name}"
    assert _check_states(win) == [Qt.CheckState.Checked, Qt.CheckState.Unchecked]

    # Select b/0001.jpg (row 1) in the Image List
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: win._file_list_image_path == str(images / "b" / "0001.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    # b/0001.jpg opens clean with 0 shapes (no leakage from a)
    assert len(win._canvas_widgets.canvas.shapes) == 0

    # Draw shape on b/0001.jpg and save
    win._commit_shapes(
        [Shape(label="box_b", points=np.array([[20.0, 20.0], [60.0, 60.0]]))]
    )
    win.save_labels(label_path=win.current_label_file_path())
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)

    # Both mirrored files exist separately
    assert (out / "a" / "0001.json").exists()
    assert (out / "b" / "0001.json").exists()
    assert _footer_text(win) == f"2 of 2 annotated in {out.name}"
    assert _check_states(win) == [Qt.CheckState.Checked, Qt.CheckState.Checked]

    # Reopen a/0001.jpg: its shape is intact
    win._docks.file_list.setCurrentRow(0)
    qtbot.waitUntil(lambda: win._file_list_image_path == str(images / "a" / "0001.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert len(win._canvas_widgets.canvas.shapes) == 1
    assert win._canvas_widgets.canvas.shapes[0].label == "box_a"


@pytest.mark.gui
@pytest.mark.parametrize("auto_save", [False, True], ids=["manual-save", "auto-save"])
def test_legacy_flat_annotation_folder_backward_compatibility(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    auto_save: bool,
) -> None:
    images = tmp_path / "images"
    (images / "a").mkdir(parents=True)
    (images / "b").mkdir(parents=True)
    a_img = images / "a" / "0001.jpg"
    b_img = images / "b" / "0001.jpg"
    shutil.copy(data_path / "raw" / "2011_000003.jpg", a_img)
    shutil.copy(data_path / "raw" / "2011_000003.jpg", b_img)

    out = tmp_path / "annotations"
    out.mkdir()
    # Create legacy flat annotation matching a_img
    flat_ann = out / "0001.json"
    flat_ann.write_text(
        json.dumps(
            {
                "version": "7.8.2",
                "flags": {},
                "shapes": [
                    {
                        "label": "legacy_box",
                        "points": [[5.0, 5.0], [25.0, 25.0]],
                        "group_id": None,
                        "description": "",
                        "shape_type": "rectangle",
                        "flags": {},
                        "mask": None,
                    }
                ],
                "imagePath": os.path.relpath(a_img, out),
                "imageData": None,
                "imageHeight": 338,
                "imageWidth": 500,
            }
        ),
        encoding="utf-8",
    )

    win = main_win(
        file_or_dir=images, output_dir=out, config_overrides={"auto_save": auto_save}
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    # Row 0 (a/0001.jpg) is checked via fallback; row 1 (b/0001.jpg) is unchecked
    assert _check_states(win) == [Qt.CheckState.Checked, Qt.CheckState.Unchecked]
    assert _footer_text(win) == f"1 of 2 annotated in {out.name}"

    # Row 0 has loaded the legacy shape
    assert len(win._canvas_widgets.canvas.shapes) == 1
    assert win._canvas_widgets.canvas.shapes[0].label == "legacy_box"

    # Row 1 opens clean with 0 shapes
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: win._file_list_image_path == str(b_img))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert len(win._canvas_widgets.canvas.shapes) == 0

    legacy_bytes = flat_ann.read_bytes()
    win._commit_shapes(
        [Shape(label="new_b", points=np.array([[10.0, 10.0], [30.0, 30.0]]))]
    )
    if not auto_save:
        win.save_labels(label_path=win.current_label_file_path())
    qtbot.waitUntil(lambda: not win._save_writer.is_busy and not win._is_changed)
    assert flat_ann.read_bytes() == legacy_bytes
    assert (out / "b" / "0001.json").exists()
    assert _check_states(win) == [Qt.CheckState.Checked, Qt.CheckState.Checked]

    win._docks.file_list.setCurrentRow(0)
    qtbot.waitUntil(lambda: win._file_list_image_path == str(a_img))
    assert win._canvas_widgets.canvas.shapes[0].label == "legacy_box"
    win._commit_shapes(
        [Shape(label="updated_a", points=np.array([[15.0, 15.0], [35.0, 35.0]]))]
    )
    if not auto_save:
        win._save_label_file(save_as=False)
    qtbot.waitUntil(lambda: not win._save_writer.is_busy and not win._is_changed)
    assert json.loads(flat_ann.read_text())["shapes"][0]["label"] == "updated_a"
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: win._file_list_image_path == str(b_img))
    assert win._canvas_widgets.canvas.shapes[0].label == "new_b"


@pytest.mark.gui
def test_same_folder_shared_stem_isolation(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    x_jpg = images / "x.jpg"
    x_png = images / "x.png"
    shutil.copy(data_path / "raw" / "2011_000003.jpg", x_jpg)
    shutil.copy(data_path / "raw" / "2011_000003.jpg", x_png)

    win = main_win(file_or_dir=images)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    # Initial check states: neither is checked
    assert _check_states(win) == [Qt.CheckState.Unchecked, Qt.CheckState.Unchecked]

    # Save annotations on row 0 (x.jpg)
    win._commit_shapes(
        [Shape(label="shape_jpg", points=np.array([[10.0, 10.0], [30.0, 30.0]]))]
    )
    win.save_labels(label_path=win.current_label_file_path())
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)
    assert (images / "x.json").exists()

    # Only row 0 is checked; row 1 (x.png) is NOT checked!
    assert _check_states(win) == [Qt.CheckState.Checked, Qt.CheckState.Unchecked]

    # Select row 1 (x.png): opens clean with 0 shapes
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: win._file_list_image_path == str(x_png))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert len(win._canvas_widgets.canvas.shapes) == 0


@pytest.mark.gui
@pytest.mark.parametrize("auto_save", [False, True], ids=["manual-save", "auto-save"])
@pytest.mark.parametrize("subfolders", [False, True], ids=["shared-stem", "dot-prefix"])
def test_colliding_images_keep_separate_annotations_after_saving_both(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auto_save: bool,
    subfolders: bool,
) -> None:
    images = tmp_path / "images"
    first = images / "..a" / "0001.jpg" if subfolders else images / "x.jpg"
    second = images / "..b" / "0001.jpg" if subfolders else images / "x.png"
    for image in (first, second):
        image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(data_path / "raw" / "2011_000003.jpg", image)
    out = tmp_path / "annotations" if subfolders else images
    out.mkdir(exist_ok=True)
    win = main_win(
        file_or_dir=images,
        output_dir=out if subfolders else None,
        config_overrides={"auto_save": auto_save},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        lambda **kwargs: (kwargs["dir"], ""),
    )

    paths: list[Path] = []
    saved_bytes: list[bytes] = []
    for row, (image, label) in enumerate(
        ((first, "first_only"), (second, "second_only"))
    ):
        win._docks.file_list.setCurrentRow(row)
        qtbot.waitUntil(lambda: win._file_list_image_path == str(image))
        assert win._image_path == str(image)
        assert not win._canvas_widgets.canvas.shapes
        destination = Path(win.current_label_file_path())
        win._commit_shapes(
            [Shape(label=label, points=np.array([[10.0, 10.0], [30.0, 30.0]]))]
        )
        if not auto_save:
            win._save_label_file(save_as=False)
        qtbot.waitUntil(lambda: not win._save_writer.is_busy and not win._is_changed)
        paths.append(destination)
        saved_bytes.append(destination.read_bytes())
        assert _check_states(win) == [
            Qt.CheckState.Checked,
            Qt.CheckState.Checked if row else Qt.CheckState.Unchecked,
        ]

    assert paths[0] != paths[1]
    assert paths[0].read_bytes() == saved_bytes[0]
    if subfolders:
        assert paths == [out / "..a" / "0001.json", out / "..b" / "0001.json"]
        assert not (out / "0001.json").exists()
    else:
        assert paths == [images / "x.json", images / "x.png.json"]
    if subfolders:
        assert _footer_text(win) == f"2 of 2 annotated in {out.name}"

    # A fresh session must reopen each Image's own Shapes, not just checkmarks.
    win.close()
    reopened = main_win(
        file_or_dir=images,
        output_dir=out if subfolders else None,
        config_overrides={"auto_save": auto_save},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=reopened)
    for row, (image, label) in enumerate(
        ((first, "first_only"), (second, "second_only"))
    ):
        reopened._docks.file_list.setCurrentRow(row)
        qtbot.waitUntil(lambda: reopened._file_list_image_path == str(image))
        assert reopened._image_path == str(image)
        assert [shape.label for shape in reopened._canvas_widgets.canvas.shapes] == [
            label
        ]
        assert reopened.current_label_file_path() == str(paths[row])
        # Later auto-save must keep the disambiguated file rather than x.json.
        reopened._commit_shapes(
            [
                Shape(
                    label=label + "_updated",
                    points=np.array([[15.0, 15.0], [35.0, 35.0]]),
                )
            ]
        )
        if not auto_save:
            reopened._save_label_file(save_as=False)
        qtbot.waitUntil(
            lambda: not reopened._save_writer.is_busy and not reopened._is_changed
        )
        assert (
            json.loads(paths[row].read_text())["shapes"][0]["label"]
            == label + "_updated"
        )


@pytest.mark.gui
def test_save_as_uses_safe_default_and_honors_explicit_overwrite(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    for name in ("x.jpg", "x.png"):
        shutil.copy(data_path / "raw" / "2011_000003.jpg", images / name)
    win = main_win(file_or_dir=images, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._commit_shapes(
        [Shape(label="first_only", points=np.array([[10.0, 10.0], [30.0, 30.0]]))]
    )
    owned = Path(win.current_label_file_path())
    assert win.save_labels(label_path=str(owned))
    before = owned.read_bytes()
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: win._file_list_image_path == str(images / "x.png"))
    win._commit_shapes(
        [Shape(label="second_only", points=np.array([[15.0, 15.0], [35.0, 35.0]]))]
    )
    assert not win.save_labels(label_path=str(owned), show_error=False)
    assert win._is_changed
    assert owned.read_bytes() == before

    default = images / "x.png.json"
    defaults: list[str] = []

    def choose_default(**kwargs: str) -> tuple[str, str]:
        defaults.append(kwargs["dir"])
        return kwargs["dir"], ""

    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", choose_default)
    win._save_label_file(save_as=True)
    assert defaults == [str(default)]
    assert win.current_label_file_path() == str(default)
    win._actions.save_auto.setChecked(True)
    win._commit_shapes(
        [Shape(label="second_updated", points=np.array([[20.0, 20.0], [40.0, 40.0]]))]
    )
    qtbot.waitUntil(lambda: not win._save_writer.is_busy and not win._is_changed)
    assert json.loads(default.read_text())["shapes"][0]["label"] == "second_updated"
    assert owned.read_bytes() == before

    # An explicit Save As choice has already passed the native overwrite
    # confirmation. Preserve that existing behavior, including later Auto Save.
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getSaveFileName", lambda **_kwargs: (str(owned), "")
    )
    win._save_label_file(save_as=True)
    assert win.current_label_file_path() == str(owned)
    assert json.loads(owned.read_text())["imagePath"] == "x.png"
    win._commit_shapes(
        [
            Shape(
                label="confirmed_overwrite", points=np.array([[5.0, 5.0], [25.0, 25.0]])
            )
        ]
    )
    qtbot.waitUntil(lambda: not win._save_writer.is_busy and not win._is_changed)
    assert json.loads(owned.read_text())["shapes"][0]["label"] == "confirmed_overwrite"


@pytest.mark.gui
@pytest.mark.parametrize("auto_save", [False, True], ids=["manual-save", "auto-save"])
def test_opened_annotation_keeps_manual_destination_and_auto_save_honors_folder(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    auto_save: bool,
) -> None:
    source = data_path / "annotated" / "2011_000003.json"
    original_bytes = source.read_bytes()
    out = tmp_path / "annotations"
    win = main_win(
        file_or_dir=source, output_dir=out, config_overrides={"auto_save": auto_save}
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    destination = out / source.name
    assert win.current_label_file_path() == str(source)
    win._commit_shapes(
        [
            Shape(
                label="copied_annotation", points=np.array([[10.0, 10.0], [30.0, 30.0]])
            )
        ]
    )
    if not auto_save:
        win._save_label_file(save_as=False)
    qtbot.waitUntil(lambda: not win._save_writer.is_busy and not win._is_changed)
    if auto_save:
        assert source.read_bytes() == original_bytes
        assert win.current_label_file_path() == str(destination)
    else:
        assert not destination.exists()
        destination = source
    assert (
        json.loads(destination.read_text())["shapes"][0]["label"] == "copied_annotation"
    )


@pytest.mark.gui
@pytest.mark.parametrize("contents", [b"{broken", b'{"shapes": []}'])
@pytest.mark.parametrize("auto_save", [False, True], ids=["manual-save", "auto-save"])
def test_damaged_disambiguated_annotation_is_not_silently_overwritten(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    critical_messages: list[str],
    contents: bytes,
    auto_save: bool,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    for name in ("x.jpg", "x.png"):
        shutil.copy(data_path / "raw" / "2011_000003.jpg", images / name)
    win = main_win(file_or_dir=images, config_overrides={"auto_save": auto_save})
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._commit_shapes(
        [Shape(label="first_only", points=np.array([[10.0, 10.0], [30.0, 30.0]]))]
    )
    if not auto_save:
        assert win.save_labels(label_path=win.current_label_file_path())
    qtbot.waitUntil(lambda: not win._save_writer.is_busy and not win._is_changed)
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: win._file_list_image_path == str(images / "x.png"))
    damaged = images / "x.png.json"
    damaged.write_bytes(contents)
    # The file can appear after opening, before the next edit/Auto Save.
    win._commit_shapes(
        [Shape(label="second_only", points=np.array([[15.0, 15.0], [35.0, 35.0]]))]
    )
    if not auto_save:
        assert not win.save_labels(label_path=str(damaged), show_error=False)
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)
    assert win._is_changed
    assert win._status_bar.save.text() == "Save failed"
    assert damaged.read_bytes() == contents
    assert not win._load_file(image_or_label_path=str(images / "x.png"))
    assert critical_messages
    assert damaged.read_bytes() == contents
    win.mark_clean()
