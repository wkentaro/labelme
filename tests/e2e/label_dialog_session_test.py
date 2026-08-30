from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._shape import Shape

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import schedule_on_dialog
from .conftest import show_window_and_wait_for_imagedata

# A modal dialog holds a nested event loop. These tests replace the session
# from inside that loop programmatically -- application modality keeps real
# user input out, so they pin the guards rather than reproduce a user gesture.
# Switching to an annotated file and to an unannotated one land differently:
# one leaves the canvas holding another file's shapes, the other leaves it
# empty, which is the state behind the reported crash.
_UNANNOTATED: Final[str] = "raw/2011_000006.jpg"


@pytest.fixture()
def make_win(main_win: MainWinFactory, qtbot: QtBot, data_path: Path) -> MainWinFactory:
    def build(**config: object) -> MainWindow:
        window = main_win(
            file_or_dir=str(data_path / "annotated"),
            config_overrides={"auto_save": False, **config},
        )
        show_window_and_wait_for_imagedata(qtbot=qtbot, win=window)
        return window

    return build


def _stage_unnamed_shape(window: MainWindow) -> None:
    # Mirrors what finalizing a drawn shape leaves behind: appended, backed up,
    # and the toolbar still in mid-draw state.
    canvas = window._canvas_widgets.canvas
    canvas.shapes.append(Shape())
    canvas.backup_shapes()
    window._on_drawing_polygon_changed(True)


def _assert_session_untouched(window: MainWindow, switched: dict[str, object]) -> None:
    # Read the dirty flag before clearing it: a failing assertion would
    # otherwise leave teardown blocked on the unsaved-changes prompt.
    changed = window._is_changed
    window.mark_clean()

    canvas = window._canvas_widgets.canvas
    assert canvas.shapes == switched["shapes"]
    assert [shape.label for shape in canvas.shapes] == switched["labels"]
    assert len(canvas.shape_backups) == switched["backups"]
    assert not changed
    # However the dialog closed, the guard has to lift the mid-draw toolbar
    # freeze, or the replacement session is stuck in it.
    assert window._actions.edit_mode.isEnabled()
    assert not window._actions.undo_last_point.isEnabled()


@pytest.mark.gui
@pytest.mark.parametrize(
    "target",
    ["annotated/2011_000006.jpg", _UNANNOTATED],
    ids=["annotated", "unannotated"],
)
@pytest.mark.parametrize(
    "dialog_result",
    [("cat", {}, None, ""), (None, None, None, None)],
    ids=["confirmed", "cancelled"],
)
def test_new_shape_ignores_dialog_answer_from_a_replaced_session(
    make_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
    dialog_result: tuple[str | None, dict | None, int | None, str | None],
    target: str,
) -> None:
    window = make_win()
    _stage_unnamed_shape(window=window)
    canvas = window._canvas_widgets.canvas
    switched: dict[str, object] = {}

    def switch_files_then_answer(*_args: object, **_kwargs: object) -> tuple:
        window._load_file(image_or_label_path=str(data_path / target))
        switched["shapes"] = canvas.shapes[:]
        switched["labels"] = [shape.label for shape in canvas.shapes]
        switched["backups"] = len(canvas.shape_backups)
        return dialog_result

    monkeypatch.setattr(window._label_dialog, "popup", switch_files_then_answer)

    window._on_new_shape()

    _assert_session_untouched(window=window, switched=switched)
    close_or_pause(qtbot=qtbot, widget=window, pause=pause)


@pytest.mark.gui
def test_new_shape_ignores_session_replaced_during_invalid_label_warning(
    make_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    # The warning box is a second nested loop, entered after the label dialog
    # has already returned, so the check has to sit downstream of both.
    window = make_win(validate_label="exact", labels=["person"])
    _stage_unnamed_shape(window=window)
    canvas = window._canvas_widgets.canvas
    monkeypatch.setattr(
        window._label_dialog, "popup", lambda *_a, **_k: ("never-seen", {}, None, "")
    )
    switched: dict[str, object] = {}

    def switch_files(*_args: object, **_kwargs: object) -> int:
        window._load_file(image_or_label_path=str(data_path / _UNANNOTATED))
        switched["shapes"] = canvas.shapes[:]
        switched["labels"] = [shape.label for shape in canvas.shapes]
        switched["backups"] = len(canvas.shape_backups)
        return 0

    monkeypatch.setattr(window, "show_error_message", switch_files)

    window._on_new_shape()

    _assert_session_untouched(window=window, switched=switched)
    close_or_pause(qtbot=qtbot, widget=window, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("keep_prev", [False, True], ids=["fresh", "keep_prev"])
def test_edit_label_ignores_dialog_answer_from_a_replaced_session(
    make_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
    keep_prev: bool,
) -> None:
    window = make_win(keep_prev=keep_prev)
    canvas = window._canvas_widgets.canvas
    window._docks.label_list.select_item(window._docks.label_list[0])
    edited = window._docks.label_list[0].shape()
    assert edited is not None
    label_before = edited.label
    switched: dict[str, object] = {}

    def switch_files_then_answer(*_args: object, **_kwargs: object) -> tuple:
        window._load_file(image_or_label_path=str(data_path / _UNANNOTATED))
        switched["shapes"] = canvas.shapes[:]
        switched["labels"] = [shape.label for shape in canvas.shapes]
        switched["backups"] = len(canvas.shape_backups)
        return "cat", {}, None, ""

    monkeypatch.setattr(window._label_dialog, "popup", switch_files_then_answer)

    window._edit_label()

    # Read the dirty flag before clearing it, or a failing assertion leaves
    # teardown blocked on the unsaved-changes prompt.
    changed = window._is_changed
    window.mark_clean()

    # The shape itself is the direct observation; carrying shapes forward keeps
    # them reachable, so a leaked rename lands on this object.
    assert edited.label == label_before
    assert len(canvas.shape_backups) == switched["backups"]
    # Carrying shapes forward dirties the new file by design.
    assert keep_prev or not changed
    assert window._docks.unique_label_list.find_label_item("cat") is None
    assert "cat" not in [shape.label for shape in canvas.shapes]
    close_or_pause(qtbot=qtbot, widget=window, pause=pause)


@pytest.mark.gui
def test_edit_label_applies_when_shapes_are_only_appended(
    make_win: MainWinFactory,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    # Pasting, duplicating and AI text-to-annotation add rows without
    # destroying anything, so the edited row survives and the rename must still
    # land. Naming a new shape is deliberately stricter -- see the guard there.
    window = make_win()
    window._docks.label_list.select_item(window._docks.label_list[0])
    edited = window._docks.label_list[0].shape()
    assert edited is not None

    rows_before = len(window._docks.label_list)

    def append_shape_then_answer(*_args: object, **_kwargs: object) -> tuple:
        window._load_shapes(shapes=[Shape(label="pasted")], replace=False)
        return "renamed", {}, None, ""

    monkeypatch.setattr(window._label_dialog, "popup", append_shape_then_answer)

    window._edit_label()

    assert len(window._docks.label_list) == rows_before + 1
    assert edited.label == "renamed"
    window.mark_clean()
    close_or_pause(qtbot=qtbot, widget=window, pause=pause)


@pytest.mark.gui
def test_keep_prev_does_not_carry_a_shape_that_is_still_being_named(
    make_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    # Carrying shapes forward reads the canvas directly, so it runs inside the
    # dialog's event loop and cannot be covered by a check made after it.
    window = make_win(keep_prev=True)
    _stage_unnamed_shape(window=window)
    canvas = window._canvas_widgets.canvas

    def switch_files_then_answer(*_args: object, **_kwargs: object) -> tuple:
        window._load_file(image_or_label_path=str(data_path / _UNANNOTATED))
        return None, None, None, None

    monkeypatch.setattr(window._label_dialog, "popup", switch_files_then_answer)

    window._on_new_shape()

    # Clear before asserting: carrying shapes forward dirties the new file by
    # design, and a failing assertion would block teardown on the prompt.
    window.mark_clean()

    assert canvas.shapes
    assert all(shape.label is not None for shape in canvas.shapes)
    close_or_pause(qtbot=qtbot, widget=window, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("accept", [True, False], ids=["confirmed", "cancelled"])
def test_new_shape_survives_a_switch_made_inside_the_live_dialog(
    make_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    accept: bool,
) -> None:
    # The other cases replace the dialog with a stub, which never enters the
    # nested loop the guard exists for. Here the real dialog is on screen and
    # the file is switched from inside its own event loop.
    window = make_win()
    _stage_unnamed_shape(window=window)
    canvas = window._canvas_widgets.canvas
    switched: dict[str, object] = {}

    def switch_files_then_close() -> None:
        window._load_file(image_or_label_path=str(data_path / _UNANNOTATED))
        switched["shapes"] = canvas.shapes[:]
        switched["labels"] = [shape.label for shape in canvas.shapes]
        switched["backups"] = len(canvas.shape_backups)
        if accept:
            window._label_dialog.edit.setText("cat")
            window._label_dialog.accept()
        else:
            window._label_dialog.reject()

    schedule_on_dialog(
        label_dialog=window._label_dialog, action=switch_files_then_close
    )

    window._on_new_shape()

    _assert_session_untouched(window=window, switched=switched)
    close_or_pause(qtbot=qtbot, widget=window, pause=pause)
