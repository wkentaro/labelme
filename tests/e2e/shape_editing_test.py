from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.widgets._shape_render import bounds as _shape_bounds
from labelme.widgets.canvas import Canvas

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import drag_canvas
from .conftest import image_to_widget_pos
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata


def _open_and_select_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    shape_index: int = 0,
    config_overrides: dict[str, bool] | None = None,
    output_dir: str | None = None,
) -> tuple[MainWindow, Canvas]:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=config_overrides,
        output_dir=output_dir,
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    assert len(canvas.shapes) == 5

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=shape_index)
    return win, canvas


def _delete_selected_shape(
    win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    monkeypatch.setattr(win, "_confirm_deletion", lambda *args, **kwargs: True)
    win.delete_selected_shapes()
    qtbot.wait(50)


@pytest.mark.gui
def test_select_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win, qtbot=qtbot, data_path=data_path
    )

    assert canvas.selected_shapes[0].label == "person"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_copy_paste_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    original_label = canvas.selected_shapes[0].label
    num_shapes_before = len(canvas.shapes)

    win._actions.copy.trigger()
    win._actions.paste.trigger()
    qtbot.wait(50)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == original_label

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_duplicate_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    num_shapes_before = len(canvas.shapes)

    win._actions.duplicate.trigger()
    qtbot.wait(50)

    assert len(canvas.shapes) == num_shapes_before + 1

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    _delete_selected_shape(win=win, monkeypatch=monkeypatch, qtbot=qtbot)

    assert len(canvas.shapes) == 4

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_undo_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    _delete_selected_shape(win=win, monkeypatch=monkeypatch, qtbot=qtbot)
    assert len(canvas.shapes) == 4

    win.undo_shape_edit()
    qtbot.wait(50)
    assert len(canvas.shapes) == 5
    assert canvas.shapes[0].label == "person"

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_right_drag_copy_here_duplicates_shape(
    qtbot: QtBot,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    original_shape = canvas.shapes[0]
    original_label = original_shape.label
    original_first_point = original_shape.points[0].copy()
    num_before = len(canvas.shapes)

    bounds_center = _shape_bounds(shape=original_shape).center()
    start_widget = image_to_widget_pos(canvas=canvas, image_pos=bounds_center)
    end_widget = QPoint(start_widget.x() + 30, start_widget.y() + 20)

    # The modal menu would block the test, so trigger "Copy here" directly
    # and return it truthy so the canvas treats the release as handled.
    copy_here_action = canvas.context_menus.with_selection.actions()[0]

    def trigger_copy_here(*args: object, **kwargs: object) -> object:
        copy_here_action.trigger()
        return copy_here_action

    monkeypatch.setattr(canvas.context_menus.with_selection, "exec", trigger_copy_here)

    drag_canvas(
        qtbot=qtbot,
        canvas=canvas,
        button=Qt.MouseButton.RightButton,
        start=start_widget,
        end=end_widget,
    )

    assert len(canvas.shapes) == num_before + 1

    # Pasted shape must be a deep copy: distinct object, distinct point list,
    # and mutation must not bleed back into the original. Guards against a
    # regression where ShapeClipboard.paste() returned shared references.
    duplicated_shape = canvas.shapes[-1]
    assert duplicated_shape is not original_shape
    assert duplicated_shape.points is not original_shape.points
    duplicated_shape.label = "mutated"
    duplicated_shape.points[0][0] += 999.0
    assert original_shape.label == original_label
    assert np.array_equal(original_shape.points[0], original_first_point)

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
