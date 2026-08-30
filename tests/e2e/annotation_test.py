from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._automation._types import AiOutputFormat
from labelme._shape import Shape

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata

# Smallest available model (~40MB) to keep download and inference fast
_AI_MODEL: Final = "efficientsam:10m"


@pytest.mark.gui
def test_labeling_ai_lands_preserves_generated_group(
    main_win: MainWinFactory,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    *,
    pause: bool,
) -> None:
    win = main_win(config_overrides={"auto_save": False})
    canvas = win._canvas_widgets.canvas
    shapes = [Shape(group_id=1), Shape(group_id=1)]
    canvas.load_shapes(shapes=shapes)
    canvas.backup_shapes()
    monkeypatch.setattr(
        win._label_dialog,
        "popup",
        lambda *_args, **_kwargs: ("land", {}, None, ""),
    )

    win._on_new_shape()

    assert [shape.label for shape in shapes] == ["land", "land"]
    assert [shape.group_id for shape in shapes] == [1, 1]

    win.mark_clean()
    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.fixture()
def ai_model_combo(raw_win: MainWindow) -> QComboBox:
    return raw_win._ai_annotation._model_combo


@pytest.mark.gui
def test_ai_points_mode_disables_sam3(
    raw_win: MainWindow,
    ai_model_combo: QComboBox,
    qtbot: QtBot,
    *,
    pause: bool,
) -> None:
    sam3_index = ai_model_combo.findData("sam3:latest")

    raw_win._actions.create_ai_points_to_shape_mode.trigger()

    assert raw_win._canvas_widgets.canvas.create_mode == "ai_points_to_shape"
    model = ai_model_combo.model()
    assert not model.flags(model.index(sam3_index, 0)) & Qt.ItemFlag.ItemIsEnabled

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_ai_points_mode_keeps_selected_sam3_and_rejects_click(
    raw_win: MainWindow,
    ai_model_combo: QComboBox,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    *,
    pause: bool,
) -> None:
    warnings: list[tuple[str, str]] = []

    def _warning(
        parent: MainWindow, title: str, message: str
    ) -> QMessageBox.StandardButton:
        assert parent is raw_win
        warnings.append((title, message))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", _warning)
    raw_win._actions.create_ai_box_to_shape_mode.trigger()
    sam3_index = ai_model_combo.findData("sam3:latest")
    ai_model_combo.setCurrentIndex(sam3_index)

    raw_win._actions.create_ai_points_to_shape_mode.trigger()

    assert raw_win._canvas_widgets.canvas.create_mode == "ai_points_to_shape"
    assert ai_model_combo.currentData() == "sam3:latest"
    model = ai_model_combo.model()
    assert not (model.flags(model.index(sam3_index, 0)) & Qt.ItemFlag.ItemIsEnabled)

    canvas = raw_win._canvas_widgets.canvas
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=canvas.rect().center())

    assert warnings == [
        (
            "AI-Points Unavailable",
            "Sam3 does not support point prompts.\n"
            "Please select a different model or use AI-Box mode.",
        )
    ]
    assert canvas._current is None

    raw_win._actions.create_ai_box_to_shape_mode.trigger()

    assert canvas.create_mode == "ai_box_to_shape"
    assert ai_model_combo.currentData() == "sam3:latest"
    assert model.flags(model.index(sam3_index, 0)) & Qt.ItemFlag.ItemIsEnabled

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    (
        "create_mode",
        "setup_clicks",
        "finalize_click",
        "finalize_modifier",
        "expected_num_points",
        "ai_output_format",
    ),
    [
        pytest.param(
            "polygon",
            [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)],
            (0.25, 0.25),
            Qt.KeyboardModifier.NoModifier,
            4,
            None,
            id="polygon",
        ),
        pytest.param(
            "rectangle",
            [(0.25, 0.25)],
            (0.75, 0.75),
            Qt.KeyboardModifier.NoModifier,
            2,
            None,
            id="rectangle",
        ),
        pytest.param(
            "oriented_rectangle",
            [(0.25, 0.5), (0.5, 0.5)],
            (0.5, 0.75),
            Qt.KeyboardModifier.NoModifier,
            4,
            None,
            id="oriented_rectangle",
        ),
        pytest.param(
            "circle",
            [(0.5, 0.5)],
            (0.75, 0.5),
            Qt.KeyboardModifier.NoModifier,
            2,
            None,
            id="circle",
        ),
        pytest.param(
            "line",
            [(0.25, 0.25)],
            (0.75, 0.75),
            Qt.KeyboardModifier.NoModifier,
            2,
            None,
            id="line",
        ),
        pytest.param(
            "point", [], (0.5, 0.5), Qt.KeyboardModifier.NoModifier, 1, None, id="point"
        ),
        pytest.param(
            "linestrip",
            [(0.25, 0.25), (0.5, 0.5)],
            (0.75, 0.75),
            Qt.KeyboardModifier.ControlModifier,
            3,
            None,
            id="linestrip",
        ),
        pytest.param(
            "ai_points_to_shape",
            [],
            (0.5, 0.5),
            Qt.KeyboardModifier.ControlModifier,
            None,
            "polygon",
            id="ai_points-polygon",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_points_to_shape",
            [],
            (0.5, 0.5),
            Qt.KeyboardModifier.ControlModifier,
            2,
            "mask",
            id="ai_points-mask",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_points_to_shape",
            [],
            (0.5, 0.5),
            Qt.KeyboardModifier.ControlModifier,
            2,
            "rectangle",
            id="ai_points-rectangle",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_points_to_shape",
            [],
            (0.5, 0.5),
            Qt.KeyboardModifier.ControlModifier,
            2,
            "circle",
            id="ai_points-circle",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_points_to_shape",
            [],
            (0.5, 0.5),
            Qt.KeyboardModifier.ControlModifier,
            4,
            "oriented_rectangle",
            id="ai_points-oriented_rectangle",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_box_to_shape",
            [(0.3, 0.3)],
            (0.7, 0.7),
            Qt.KeyboardModifier.NoModifier,
            None,
            "polygon",
            id="ai_box-polygon",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_box_to_shape",
            [(0.3, 0.3)],
            (0.7, 0.7),
            Qt.KeyboardModifier.NoModifier,
            2,
            "mask",
            id="ai_box-mask",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_box_to_shape",
            [(0.3, 0.3)],
            (0.7, 0.7),
            Qt.KeyboardModifier.NoModifier,
            2,
            "rectangle",
            id="ai_box-rectangle",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_box_to_shape",
            [(0.3, 0.3)],
            (0.7, 0.7),
            Qt.KeyboardModifier.NoModifier,
            2,
            "circle",
            id="ai_box-circle",
            marks=pytest.mark.network,
        ),
        pytest.param(
            "ai_box_to_shape",
            [(0.3, 0.3)],
            (0.7, 0.7),
            Qt.KeyboardModifier.NoModifier,
            4,
            "oriented_rectangle",
            id="ai_box-oriented_rectangle",
            marks=pytest.mark.network,
        ),
    ],
)
@pytest.mark.usefixtures("close_failed_download_dialog")
def test_annotate_shape_types(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    *,
    pause: bool,
    create_mode: str,
    setup_clicks: list[tuple[float, float]],
    finalize_click: tuple[float, float],
    finalize_modifier: Qt.KeyboardModifier,
    expected_num_points: int | None,
    ai_output_format: AiOutputFormat | None,
) -> None:
    expected_shape_type = ai_output_format if ai_output_format else create_mode

    input_file = str(data_path / "raw/2011_000003.jpg")
    out_file = str(tmp_path / "2011_000003.json")

    win = main_win(
        file_or_dir=input_file,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label = "test_shape"
    canvas = win._canvas_widgets.canvas
    canvas.set_ai_model_name(_AI_MODEL)
    if ai_output_format is not None:
        canvas.set_ai_output_format(ai_output_format)

    canvas_size = canvas.size()

    def to_pos(xy: tuple[float, float]) -> QPoint:
        return QPoint(
            int(canvas_size.width() * xy[0]),
            int(canvas_size.height() * xy[1]),
        )

    win._switch_canvas_mode(edit=False, create_mode=create_mode)
    qtbot.wait(50)

    def click(
        xy: tuple[float, float],
        modifier: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    ) -> None:
        pos = to_pos(xy)
        qtbot.mouseMove(canvas, pos=pos)
        qtbot.wait(50)
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, modifier, pos=pos)
        qtbot.wait(50)

    for xy in setup_clicks:
        click(xy=xy)

    def enter_label_when_visible() -> None:
        if not win._label_dialog.isVisible():
            QTimer.singleShot(50, enter_label_when_visible)
            return
        qtbot.keyClicks(win._label_dialog.edit, label)
        qtbot.wait(50)
        qtbot.keyClick(win._label_dialog.edit, Qt.Key.Key_Enter)

    QTimer.singleShot(0, enter_label_when_visible)

    click(xy=finalize_click, modifier=finalize_modifier)

    shapes = canvas.shapes
    assert len(shapes) >= 1
    assert all(shape.label == label for shape in shapes)
    assert all(shape.shape_type == expected_shape_type for shape in shapes)
    assert all(shape.flags == {} for shape in shapes)
    assert all(
        (shape.mask is not None) == (expected_shape_type == "mask") for shape in shapes
    )
    if expected_shape_type == "polygon" and len(shapes) > 1:
        assert shapes[0].group_id is not None
        assert all(shape.group_id == shapes[0].group_id for shape in shapes)
    else:
        assert all(shape.group_id is None for shape in shapes)
    if expected_num_points is not None:
        assert len(shapes[0].points) == expected_num_points

    win._save_label_file(save_as=False)
    assert_labelfile_sanity(out_file)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
