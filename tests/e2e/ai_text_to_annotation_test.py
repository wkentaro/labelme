from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Final
from unittest.mock import MagicMock

import numpy as np
import osam.types
import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._automation import AiOutputFormat
from labelme._automation import InferenceRequest
from labelme._automation import OsamWorker
from labelme._automation import _osam_session
from labelme._automation import _osam_worker
from labelme._shape import Shape
from labelme._widgets._label_dialog import LabelDialog
from labelme._widgets._label_dialog import LabelDialogEntry

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import image_to_widget_pos
from .conftest import show_window_and_wait_for_imagedata

if TYPE_CHECKING:
    from labelme._app import MainWindow

pytestmark = pytest.mark.usefixtures("cached_ai_models")

_AI_TEXT_MODEL: Final = "sam3:latest"


@pytest.fixture(autouse=True)
def popups(*, monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    # Each AI-Detect batch asks for its label once; accept the prefill.
    texts: list[str | None] = []

    def popup(
        self: LabelDialog, *, text: str | None = None, **_: object
    ) -> LabelDialogEntry:
        del self
        texts.append(text)
        return LabelDialogEntry(
            label=text or "object", flags={}, group_id=None, description=""
        )

    monkeypatch.setattr(LabelDialog, "popup", popup)
    return texts


def _make_response(
    *,
    texts: list[str],
    boxes: list[tuple[int, int, int, int]],
    scores: list[float],
    label_indices: list[int],
    with_masks: bool,
) -> osam.types.GenerateResponse:
    annotations = []
    for (xmin, ymin, xmax, ymax), score, label_idx in zip(
        boxes, scores, label_indices, strict=True
    ):
        mask = None
        if with_masks:
            mask = np.ones((ymax - ymin + 1, xmax - xmin + 1), dtype=bool)
        annotations.append(
            osam.types.Annotation(
                bounding_box=osam.types.BoundingBox(
                    xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax
                ),
                text=texts[label_idx],
                score=score,
                mask=mask,
            )
        )
    return osam.types.GenerateResponse(model=_AI_TEXT_MODEL, annotations=annotations)


def _make_person_response(
    *, texts: list[str], with_masks: bool
) -> osam.types.GenerateResponse:
    person_idx = texts.index("person")
    return _make_response(
        texts=texts,
        boxes=[(50, 30, 200, 300), (220, 40, 350, 290)],
        scores=[0.85, 0.45],
        label_indices=[person_idx, person_idx],
        with_masks=with_masks,
    )


def _make_edge_crossing_response(*, texts: list[str]) -> osam.types.GenerateResponse:
    return _make_response(
        texts=texts,
        boxes=[(-10, 30, 50, 100)],
        scores=[0.9],
        label_indices=[0],
        with_masks=False,
    )


def _install_mock_session(
    *,
    monkeypatch: pytest.MonkeyPatch,
    response_fn: Callable[..., osam.types.GenerateResponse],
) -> None:
    mock_session = MagicMock()
    mock_session.run = MagicMock(
        side_effect=lambda **kw: response_fn(texts=kw["texts"])
    )
    monkeypatch.setitem(_osam_session._SESSIONS, _AI_TEXT_MODEL, mock_session)

    # Runs the request in this process, where the mock session lives.
    def submit(
        self: OsamWorker, *, channel: object, job: object, request: InferenceRequest
    ) -> None:
        del channel
        assert request.image is not None
        try:
            annotations = _osam_worker._run(
                _osam_session.get_osam_session(model_name=request.model_name),
                request,
                request.image,
            )
        except Exception as e:
            self.failed.emit(job, f"{type(e).__name__}: {e}")
        else:
            self.finished.emit(job, annotations)

    monkeypatch.setattr(OsamWorker, "submit", submit)


def _set_output_like_tool(*, win: MainWindow, create_mode: str) -> None:
    # Run detects with the shared AI Output; match it to a Rectangle or
    # Polygon tool so YOLO-World (boxes only) can answer.
    output_combo = win._ai_annotation._output_format_combo
    if (index := output_combo.findData(create_mode)) >= 0:
        output_combo.setCurrentIndex(index)


def _run_text_prompt(
    *,
    win: MainWindow,
    qtbot: QtBot,
    text: str,
    create_mode: str,
    score_threshold: float,
) -> None:
    win._switch_canvas_mode(edit=False, create_mode=create_mode)
    _set_output_like_tool(win=win, create_mode=create_mode)
    qtbot.wait(50)

    win._ai_text._text_input.setText(text)
    win._ai_text._score_spinbox.setValue(score_threshold)
    win._ai_text._iou_spinbox.setValue(0.5)

    combo = win._ai_text._model_combo
    for i in range(combo.count()):
        if combo.itemData(i) == _AI_TEXT_MODEL:
            combo.setCurrentIndex(i)
            break

    win._submit_ai_prompt()
    qtbot.wait(100)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("create_mode", "expected_shape_type", "text", "response_fn", "expected_labels"),
    [
        pytest.param(
            "rectangle",
            "rectangle",
            "person",
            functools.partial(_make_person_response, with_masks=False),
            {"person"},
            id="rectangle",
        ),
        pytest.param(
            "polygon",
            "polygon",
            "person",
            functools.partial(_make_person_response, with_masks=True),
            {"person"},
            id="polygon",
        ),
        pytest.param(
            "ai_box_to_shape",
            "polygon",
            "person",
            functools.partial(_make_person_response, with_masks=True),
            {"person"},
            id="ai_box-polygon",
        ),
        pytest.param(
            "ai_box_to_shape",
            "oriented_rectangle",
            "person",
            _make_edge_crossing_response,
            {"person"},
            id="ai_box-oriented_rectangle-at-edge",
        ),
    ],
)
def test_text_prompt_creates_shapes(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    create_mode: str,
    expected_shape_type: AiOutputFormat,
    text: str,
    response_fn: Callable[..., osam.types.GenerateResponse],
    expected_labels: set[str],
) -> None:
    input_file = str(data_path / "raw/2011_000003.jpg")
    win = main_win(
        file_or_dir=input_file,
        config_overrides=dict(auto_save=True, label_flags={".*": ["occluded"]}),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    assert len(canvas.shapes) == 0

    if create_mode == "ai_box_to_shape":
        output_combo = win._ai_annotation._output_format_combo
        output_combo.setCurrentIndex(output_combo.findData(expected_shape_type))

    _install_mock_session(monkeypatch=monkeypatch, response_fn=response_fn)
    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text=text,
        create_mode=create_mode,
        score_threshold=0.1,
    )

    assert canvas.create_mode == "ai_detect"
    assert len(canvas.shapes) >= 1
    labels = {shape.label for shape in canvas.shapes}
    assert labels == expected_labels
    for shape in canvas.shapes:
        assert shape.flags == {"occluded": False}
        assert shape.shape_type == expected_shape_type
        if shape.shape_type == "oriented_rectangle":
            assert (shape.points >= 0).all()
            assert (shape.points <= [win._image.width(), win._image.height()]).all()

    out_file = str(tmp_path / "2011_000003.json")
    win._save_label_file(save_as=False)
    assert_labelfile_sanity(out_file)

    win._actions.undo.trigger()
    assert not canvas.shapes
    assert not canvas.can_restore_shape
    assert not win._actions.undo.isEnabled()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("create_mode", "output_format"),
    [
        pytest.param("polygon", None, id="polygon"),
        pytest.param("ai_box_to_shape", "mask", id="ai_box-mask"),
    ],
)
def test_box_only_model_is_rejected_before_inference(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    create_mode: str,
    output_format: AiOutputFormat | None,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        config_overrides={"ai": {"text_model": "yoloworld:latest"}},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    if output_format is not None:
        output_combo = win._ai_annotation._output_format_combo
        output_combo.setCurrentIndex(output_combo.findData(output_format))
    win._switch_canvas_mode(edit=False, create_mode=create_mode)
    win._ai_text._text_input.setText("person")

    submitted: list[object] = []
    monkeypatch.setattr(OsamWorker, "submit", lambda *_, **kw: submitted.append(kw))
    readiness_checks: list[str] = []
    monkeypatch.setattr(win, "_ensure_ai_model_ready", readiness_checks.append)
    warnings: list[str] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda _parent, title, _text: warnings.append(title),
    )

    win._submit_ai_prompt()

    assert readiness_checks == []
    assert submitted == []
    assert warnings == ["Mask Output Unavailable"]
    assert win._config["ai"]["text_model"] == "yoloworld:latest"
    combo = win._ai_text._model_combo
    assert combo.currentData() == "yoloworld:latest"
    model = combo.model()
    yolo_index = combo.findData("yoloworld:latest")
    assert not model.flags(model.index(yolo_index, 0)) & Qt.ItemFlag.ItemIsEnabled
    win._open_settings()
    assert win._settings_dialog is not None
    editor = win._settings_dialog._editors[("ai", "text_model")]
    assert isinstance(editor, QtWidgets.QComboBox)
    settings_model = editor.model()
    settings_index = settings_model.index(editor.findData("yoloworld:latest"), 0)
    assert not settings_model.flags(settings_index) & Qt.ItemFlag.ItemIsEnabled

    # Run creates Shapes in the Output whatever the tool, so only the Output
    # makes a box-only model usable again.
    win._switch_canvas_mode(edit=False, create_mode="rectangle")
    assert not model.flags(model.index(yolo_index, 0)) & Qt.ItemFlag.ItemIsEnabled
    output_combo = win._ai_annotation._output_format_combo
    output_combo.setCurrentIndex(output_combo.findData("rectangle"))
    assert model.flags(model.index(yolo_index, 0)) & Qt.ItemFlag.ItemIsEnabled
    assert settings_model.flags(settings_index) & Qt.ItemFlag.ItemIsEnabled

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_nms_deduplicates_existing_shapes(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    input_file = str(data_path / "raw/2011_000003.jpg")
    win = main_win(file_or_dir=input_file)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas

    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=functools.partial(_make_person_response, with_masks=False),
    )

    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="person",
        create_mode="rectangle",
        score_threshold=0.1,
    )
    first_run_count = len(canvas.shapes)
    assert first_run_count == 2
    assert win.statusBar().currentMessage() == "Found 2 new 'person'"

    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="person",
        create_mode="rectangle",
        score_threshold=0.1,
    )
    assert len(canvas.shapes) == first_run_count
    assert win.statusBar().currentMessage() == "No new 'person' found"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_score_threshold_filters_detections(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    input_file = str(data_path / "raw/2011_000003.jpg")
    win = main_win(file_or_dir=input_file)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas

    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=functools.partial(_make_person_response, with_masks=False),
    )

    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="person",
        create_mode="rectangle",
        score_threshold=0.01,
    )
    low_threshold_count = len(canvas.shapes)
    assert low_threshold_count == 2

    canvas.shapes.clear()
    canvas.update()

    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="person",
        create_mode="rectangle",
        score_threshold=0.5,
    )
    high_threshold_count = len(canvas.shapes)
    assert high_threshold_count == 1

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("failure_stage", ["inference", "postprocessing"])
def test_text_prompt_error_preserves_annotation(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    failure_stage: str,
) -> None:
    win = main_win(file_or_dir=str(data_path / "annotated/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    previous_shapes = canvas.shapes[:]
    assert previous_shapes

    def _raise(**_: object) -> osam.types.GenerateResponse:
        raise RuntimeError("boom")

    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=(
            _raise
            if failure_stage == "inference"
            else functools.partial(_make_person_response, with_masks=False)
        ),
    )
    if failure_stage == "postprocessing":
        monkeypatch.setattr("labelme._automation._text_detection.nms_bboxes", _raise)
    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="person",
        create_mode="rectangle",
        score_threshold=0.1,
    )

    assert win.isVisible()
    assert canvas.shapes == previous_shapes
    assert "AI inference failed" in win.statusBar().currentMessage()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_canvas_inference_failed_signal_surfaces_status_message(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    # The hover-preview path emits inference_failed from inside paintEvent, so
    # the signal is wired with a queued connection. Emitting it must still
    # surface the status message once the event loop runs.
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    win._canvas_widgets.canvas.inference_failed.emit("RuntimeError: boom")
    qtbot.waitUntil(
        lambda: "AI inference failed" in win.statusBar().currentMessage(),
        timeout=1000,
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_text_result_waits_for_the_label_dialog(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=functools.partial(_make_person_response, with_masks=False),
    )
    win._switch_canvas_mode(edit=False, create_mode="rectangle")
    _set_output_like_tool(win=win, create_mode="rectangle")
    win._ai_text._text_input.setText("person")
    win._ai_text._score_spinbox.setValue(0.1)
    combo = win._ai_text._model_combo
    combo.setCurrentIndex(combo.findData(_AI_TEXT_MODEL))

    def popup(*, text: str | None = None, **_: object) -> LabelDialogEntry:
        if text == "person":  # The batch's own dialog, after the first closes.
            return LabelDialogEntry(label=text, flags={}, group_id=None, description="")
        # The result lands while the user types the drawn shape's label.
        dialog = QtWidgets.QDialog(win)
        dialog.setModal(True)
        dialog.show()
        win._submit_ai_prompt()
        qtbot.wait(300)
        assert [s.label for s in canvas.shapes] == [None]
        dialog.close()
        return LabelDialogEntry(label="manual", flags={}, group_id=None, description="")

    monkeypatch.setattr(win._label_dialog, "popup", popup)
    canvas.shapes.append(
        Shape(shape_type="rectangle", points=np.array([(0.0, 0.0), (10.0, 10.0)]))
    )
    canvas.backup_shapes()

    win._on_new_shape()

    qtbot.waitUntil(lambda: len(canvas.shapes) == 3)
    assert [s.label for s in canvas.shapes] == ["manual", "person", "person"]


def _hold_text_results(
    *,
    win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    create_mode: str,
) -> Callable[[], None]:
    # Starts a text prompt now and returns what delivers its result later.
    held: list[tuple[OsamWorker, object, object]] = []

    def submit(
        self: OsamWorker, *, channel: object, job: object, request: InferenceRequest
    ) -> None:
        del channel
        assert request.image is not None
        held.append(
            (
                self,
                job,
                _osam_worker._run(
                    _osam_session.get_osam_session(model_name=request.model_name),
                    request,
                    request.image,
                ),
            )
        )

    monkeypatch.setattr(OsamWorker, "submit", submit)
    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="person",
        create_mode=create_mode,
        score_threshold=0.1,
    )
    ((worker, job, annotations),) = held
    return lambda: worker.finished.emit(job, annotations)


@pytest.mark.gui
def test_text_result_waits_for_the_draft(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=functools.partial(_make_person_response, with_masks=True),
    )
    deliver = _hold_text_results(
        win=win, qtbot=qtbot, monkeypatch=monkeypatch, create_mode="polygon"
    )
    # Run switched to AI-Detect; the user picks Polygon again and draws.
    win._switch_canvas_mode(edit=False, create_mode="polygon")
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=(0.5, 0.5))

    deliver()
    qtbot.wait(300)
    assert canvas.is_drawing
    assert canvas.shapes == []

    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: len(canvas.shapes) == 2)
    assert win._actions.undo.isEnabled()


@pytest.mark.gui
def test_text_result_waits_for_a_drag(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=functools.partial(_make_person_response, with_masks=False),
    )
    box = Shape(
        label="box",
        shape_type="rectangle",
        points=np.array([(400.0, 20.0), (460.0, 80.0)]),
    )
    win._load_shapes([box], replace=True)
    deliver = _hold_text_results(
        win=win, qtbot=qtbot, monkeypatch=monkeypatch, create_mode="rectangle"
    )
    win._switch_canvas_mode(edit=True, create_mode=None)

    def at(x: float) -> QPoint:
        return image_to_widget_pos(canvas=canvas, image_pos=QPointF(x, 50))

    qtbot.mouseMove(canvas, pos=at(430))
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=at(430))
    qtbot.mouseMove(canvas, pos=at(440))
    deliver()  # lands mid-drag
    qtbot.mouseMove(canvas, pos=at(450))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=at(450))
    qtbot.waitUntil(lambda: len(canvas.shapes) == 3)

    xmins = []
    while win._actions.undo.isEnabled():
        win._actions.undo.trigger()
        if canvas.shapes:
            xmins.append(float(canvas.shapes[0].points[:, 0].min()))
    # Undo steps back over the result, then the whole drag, never mid-drag.
    assert xmins == [pytest.approx(420, abs=2), 400.0]


@pytest.mark.gui
def test_text_result_waits_for_a_held_vertex(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=functools.partial(_make_person_response, with_masks=False),
    )
    box = Shape(
        label="box",
        shape_type="rectangle",
        points=np.array([(400.0, 20.0), (460.0, 80.0)]),
    )
    win._load_shapes([box], replace=True)
    deliver = _hold_text_results(
        win=win, qtbot=qtbot, monkeypatch=monkeypatch, create_mode="rectangle"
    )
    win._switch_canvas_mode(edit=True, create_mode=None)

    def at(x: float) -> QPoint:
        return image_to_widget_pos(canvas=canvas, image_pos=QPointF(x, 20))

    qtbot.mouseMove(canvas, pos=at(400))
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=at(400))
    deliver()  # lands before the corner moves
    qtbot.mouseMove(canvas, pos=at(420))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=at(420))
    qtbot.waitUntil(lambda: len(canvas.shapes) == 3)

    assert canvas.shapes[0].points[0, 0] == pytest.approx(420, abs=2)


@pytest.mark.gui
def test_text_result_keeps_the_selection_editable(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=functools.partial(_make_person_response, with_masks=False),
    )
    box = Shape(
        label="box",
        shape_type="rectangle",
        points=np.array([(400.0, 20.0), (460.0, 80.0)]),
    )
    win._load_shapes([box], replace=True)
    deliver = _hold_text_results(
        win=win, qtbot=qtbot, monkeypatch=monkeypatch, create_mode="rectangle"
    )
    win._switch_canvas_mode(edit=True, create_mode=None)
    canvas.select_shapes(shapes=[box])

    deliver()

    assert len(canvas.shapes) == 3
    assert canvas.selected_shapes == [box]
    assert [i.shape() for i in win._docks.label_list.selected_items()] == [box]
    monkeypatch.setattr(
        win._label_dialog,
        "popup",
        lambda **_: LabelDialogEntry(
            label="renamed", flags={}, group_id=None, description=""
        ),
    )
    win._actions.edit.trigger()
    assert box.label == "renamed"


@pytest.mark.gui
def test_empty_text_prompt_asks_for_a_prompt(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._switch_canvas_mode(edit=False, create_mode="polygon")

    win._submit_ai_prompt()

    assert win.statusBar().currentMessage() == "Type what to detect"
    assert win._canvas_widgets.canvas.create_mode == "polygon"


@pytest.mark.gui
def test_text_prompt_without_an_image_does_nothing(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=functools.partial(_make_person_response, with_masks=False),
    )
    win._ai_text._text_input.setText("person")

    win._submit_ai_prompt()

    assert win._canvas_widgets.canvas.shapes == []


@pytest.mark.gui
def test_ai_detect_box_reads_the_picker_at_use(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    combo = win._ai_text._model_combo
    combo.setCurrentIndex(combo.findData(_AI_TEXT_MODEL))

    assert win._canvas_widgets.canvas.get_ai_detect_model_name() == _AI_TEXT_MODEL


@pytest.mark.gui
def test_ai_detect_box_checks_the_model_setting_before_download(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        config_overrides={"ai": {"text_model": "sam3:latest"}},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    monkeypatch.setattr(win._model_manager, "is_ready", lambda _name: False)
    win._refresh_model_availability()
    assert win._ai_text.get_model_name() == ""

    # Not downloaded yet, but compatible: the box is accepted, so the Models
    # window can offer the download.
    win._switch_canvas_mode(edit=False, create_mode="ai_detect")
    assert not win._canvas_widgets.canvas._refuses_example_box()


@pytest.mark.gui
def test_text_prompt_is_one_concept(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    sent: list[list[str]] = []

    def respond(*, texts: list[str]) -> osam.types.GenerateResponse:
        sent.append(texts)
        return _make_response(
            texts=texts,
            boxes=[(50, 30, 200, 300)],
            scores=[0.85],
            label_indices=[0],
            with_masks=False,
        )

    _install_mock_session(monkeypatch=monkeypatch, response_fn=respond)
    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text=" person, sofa ",
        create_mode="rectangle",
        score_threshold=0.1,
    )

    assert sent == [["person, sofa"]]
    shapes = win._canvas_widgets.canvas.shapes
    assert shapes
    assert {s.label for s in shapes} == {"person, sofa"}


@pytest.mark.gui
@pytest.mark.parametrize(("chosen", "labels"), [("dog", ["dog", "dog"]), (None, [])])
def test_one_dialog_labels_the_whole_batch(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    chosen: str | None,
    labels: list[str],
) -> None:
    # The query is a prompt: "black dog" isn't a Label, but finds dogs.
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        config_overrides=dict(labels=["dog"], validate_label="exact"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=lambda *, texts: _make_response(
            texts=texts,
            boxes=[(50, 30, 200, 300), (220, 40, 350, 290)],
            scores=[0.85, 0.45],
            label_indices=[0, 0],
            with_masks=False,
        ),
    )
    texts: list[str | None] = []

    def popup(*, text: str | None = None, **_: object) -> LabelDialogEntry | None:
        texts.append(text)
        if chosen is None:
            return None  # Cancel
        return LabelDialogEntry(label=chosen, flags={}, group_id=None, description="")

    monkeypatch.setattr(win._label_dialog, "popup", popup)
    undo_enabled = win._actions.undo.isEnabled()

    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="black dog",
        create_mode="rectangle",
        score_threshold=0.1,
    )

    assert texts == ["black dog"]
    assert [s.label for s in win._canvas_widgets.canvas.shapes] == labels
    assert [s.label for i in win._docks.label_list if (s := i.shape())] == labels
    if chosen is None:
        assert win._actions.undo.isEnabled() == undo_enabled  # No undo step.


@pytest.mark.gui
@pytest.mark.parametrize(
    ("existing", "chosen", "added"),
    [
        ("dog", "dog", 0),
        ("dog", "cat", 1),
        ("black dog", "black dog", 0),
        ("black dog", "dog", 1),
    ],
)
def test_batch_skips_what_shapes_with_its_label_cover(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    existing: str,
    chosen: str,
    added: int,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    dog = Shape(
        label=existing,
        shape_type="rectangle",
        points=np.array([(50.0, 30.0), (200.0, 300.0)]),
    )
    win._load_shapes([dog], replace=True)
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=lambda *, texts: _make_response(
            texts=texts,
            boxes=[(50, 30, 200, 300)],
            scores=[0.85],
            label_indices=[0],
            with_masks=False,
        ),
    )
    monkeypatch.setattr(
        win._label_dialog,
        "popup",
        lambda **_: LabelDialogEntry(
            label=chosen, flags={}, group_id=None, description=""
        ),
    )

    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="black dog",
        create_mode="rectangle",
        score_threshold=0.1,
    )

    assert [s.label for s in win._canvas_widgets.canvas.shapes] == [
        existing,
        *[chosen] * added,
    ]
    # Named by the label the batch took, not the query.
    assert win.statusBar().currentMessage() == (
        f"Found 1 new '{chosen}'" if added else f"No new '{chosen}' found"
    )


@pytest.mark.gui
def test_empty_batch_asks_for_no_label(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    popups: list[str | None],
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    _install_mock_session(
        monkeypatch=monkeypatch,
        response_fn=lambda *, texts: _make_response(
            texts=texts, boxes=[], scores=[], label_indices=[], with_masks=False
        ),
    )

    _run_text_prompt(
        win=win, qtbot=qtbot, text="dog", create_mode="rectangle", score_threshold=0.1
    )

    assert popups == []
    assert win.statusBar().currentMessage() == "No new 'dog' found"


@pytest.mark.gui
def test_label_list_suggests_the_text_prompt(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        config_overrides=dict(labels=["person", "sofa"]),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    completer = win._ai_text._text_input.completer()
    assert completer is not None

    completer.setCompletionPrefix("OF")

    assert completer.currentCompletion() == "sofa"


@pytest.mark.gui
@pytest.mark.parametrize(("chosen", "labels"), [("dog", ["dog", "dog"]), (None, [])])
def test_one_dialog_labels_an_example_box_batch(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    chosen: str | None,
    labels: list[str],
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    texts: list[str | None] = []

    def popup(*, text: str | None = None, **_: object) -> LabelDialogEntry | None:
        texts.append(text)
        if chosen is None:
            return None  # Cancel
        return LabelDialogEntry(label=chosen, flags={}, group_id=None, description="")

    monkeypatch.setattr(win._label_dialog, "popup", popup)
    win._switch_canvas_mode(edit=False, create_mode="ai_detect")
    backups = len(canvas.shape_backups)
    for x in (0.0, 20.0):
        canvas.shapes.append(
            Shape(shape_type="rectangle", points=np.array([(x, 0.0), (x + 10, 10.0)]))
        )
    canvas.backup_shapes()

    canvas.new_shape.emit("black dog")

    assert texts == ["black dog"]
    assert [s.label for s in canvas.shapes] == labels
    assert len(canvas.shape_backups) == backups + (1 if labels else 0)


@pytest.mark.gui
def test_run_with_an_example_box_draft_refines_it(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    sent: list[tuple[list[str], list[int]]] = []

    def respond(
        *, texts: list[str], point_labels: np.ndarray, **_: object
    ) -> osam.types.GenerateResponse:
        sent.append((texts, point_labels.tolist()))
        return _make_person_response(texts=["person"], with_masks=False)

    session = MagicMock()
    session.run = MagicMock(side_effect=respond)
    monkeypatch.setitem(_osam_session._SESSIONS, "sam3:latest", session)

    def submit(
        self: OsamWorker, *, channel: object, job: object, request: InferenceRequest
    ) -> None:
        del channel
        assert request.image is not None
        self.finished.emit(job, _osam_worker._run(session, request, request.image))

    monkeypatch.setattr(OsamWorker, "submit", submit)
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    monkeypatch.setattr(win, "_ensure_ai_model_ready", lambda *_: True)
    combo = win._ai_text._model_combo
    combo.setCurrentIndex(combo.findData("sam3:latest"))
    _set_output_like_tool(win=win, create_mode="rectangle")
    win._switch_canvas_mode(edit=False, create_mode="ai_detect")
    for x, y in ((50.0, 30.0), (200.0, 300.0)):
        pos = image_to_widget_pos(canvas=canvas, image_pos=QPointF(x, y))
        qtbot.mouseMove(canvas, pos=pos)
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos)
    assert canvas.has_ai_detect_draft

    win._submit_ai_prompt()  # No query yet: refines like the example.
    win._ai_text._text_input.setText("person")
    win._submit_ai_prompt()

    assert [texts for texts, _ in sent] == [["visual"], ["visual"], ["person"]]
    assert [labels for _, labels in sent] == [[2, 3], [2, 3], [2, 3]]
    assert canvas.shapes == []
    assert len(canvas._ai_detect_draft) == 2
    assert win.focusWidget() is canvas  # So Enter and Esc reach the draft.

    # A rerun running past the ring's delay rings at its last example.
    held: list[tuple[object, InferenceRequest]] = []
    monkeypatch.setattr(
        OsamWorker,
        "submit",
        lambda _self, *, job, request, **_: held.append((job, request)),
    )
    monkeypatch.setattr(canvas, "_ai_finalize_clock", MagicMock(elapsed=lambda: 1000))
    win._submit_ai_prompt()
    assert canvas._ai_progress_center() is not None
    canvas.grab()
    ((job, request),) = held
    assert request.image is not None
    win._osam_worker.finished.emit(
        job, _osam_worker._run(session, request, request.image)
    )
    monkeypatch.setattr(OsamWorker, "submit", submit)
    assert len(canvas._ai_detect_draft) == 2


@pytest.mark.gui
@pytest.mark.parametrize(("chosen", "labels"), [("dog", ["dog", "dog"]), (None, [])])
def test_enter_asks_once_for_the_draft_label(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    chosen: str | None,
    labels: list[str],
) -> None:
    session = MagicMock()
    session.run = MagicMock(
        side_effect=lambda *, texts, **_: _make_response(
            texts=texts,
            boxes=[(50, 30, 200, 300), (220, 40, 350, 290)],
            scores=[0.85, 0.75],
            label_indices=[0, 0],
            with_masks=False,
        )
    )
    monkeypatch.setitem(_osam_session._SESSIONS, "sam3:latest", session)

    def submit(
        self: OsamWorker, *, channel: object, job: object, request: InferenceRequest
    ) -> None:
        del channel
        assert request.image is not None
        self.finished.emit(job, _osam_worker._run(session, request, request.image))

    monkeypatch.setattr(OsamWorker, "submit", submit)
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    monkeypatch.setattr(win, "_ensure_ai_model_ready", lambda *_: True)
    combo = win._ai_text._model_combo
    combo.setCurrentIndex(combo.findData("sam3:latest"))
    _set_output_like_tool(win=win, create_mode="rectangle")
    win._ai_text._text_input.setText("black dog")
    win._switch_canvas_mode(edit=False, create_mode="ai_detect")
    texts: list[str | None] = []

    def popup(*, text: str | None = None, **_: object) -> LabelDialogEntry | None:
        texts.append(text)
        if chosen is None:
            return None  # Cancel
        return LabelDialogEntry(label=chosen, flags={}, group_id=None, description="")

    monkeypatch.setattr(win._label_dialog, "popup", popup)
    for x, y in ((40.0, 20.0), (210.0, 310.0)):
        pos = image_to_widget_pos(canvas=canvas, image_pos=QPointF(x, y))
        qtbot.mouseMove(canvas, pos=pos)
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos)
    assert len(canvas._ai_detect_draft) == 2
    assert texts == []  # The draft asks nothing until Enter.

    qtbot.keyClick(canvas, Qt.Key.Key_Return)

    assert texts == ["black dog"]
    assert [s.label for s in canvas.shapes] == labels
    assert not canvas.has_ai_detect_draft
