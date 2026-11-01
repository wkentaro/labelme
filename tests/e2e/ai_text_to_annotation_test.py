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

_AI_TEXT_MODEL: Final = "yoloworld:latest"


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


def _make_multi_label_response(*, texts: list[str]) -> osam.types.GenerateResponse:
    response = _make_response(
        texts=["person", "sofa"],
        boxes=[(50, 30, 200, 300), (10, 150, 400, 330)],
        scores=[0.85, 0.70],
        label_indices=[0, 1],
        with_masks=False,
    )
    response.annotations = [a for a in response.annotations if a.text in texts]
    return response


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
            annotations = _osam_worker._run(request, request.image)
        except Exception as e:
            self.failed.emit(job, f"{type(e).__name__}: {e}")
        else:
            self.finished.emit(job, annotations)

    monkeypatch.setattr(OsamWorker, "submit", submit)


def _run_text_prompt(
    *,
    win: MainWindow,
    qtbot: QtBot,
    text: str,
    create_mode: str,
    score_threshold: float,
) -> None:
    win._switch_canvas_mode(edit=False, create_mode=create_mode)
    qtbot.wait(50)

    win._ai_text._text_input.setText(text)
    win._ai_text._score_spinbox.setValue(score_threshold)
    win._ai_text._iou_spinbox.setValue(0.5)

    combo = win._ai_text._model_combo
    for i in range(combo.count()):
        if combo.itemData(i) == _AI_TEXT_MODEL:
            combo.setCurrentIndex(i)
            break

    win._submit_ai_prompt(False)  # noqa: FBT003 -- the slot takes the Qt clicked flag positionally
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
        pytest.param(
            "rectangle",
            "rectangle",
            "person,sofa",
            _make_multi_label_response,
            {"person", "sofa"},
            id="multiple-labels",
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

    _run_text_prompt(
        win=win,
        qtbot=qtbot,
        text="person",
        create_mode="rectangle",
        score_threshold=0.1,
    )
    assert len(canvas.shapes) == first_run_count

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
    win._ai_text._text_input.setText("person")
    win._ai_text._score_spinbox.setValue(0.1)
    combo = win._ai_text._model_combo
    combo.setCurrentIndex(combo.findData(_AI_TEXT_MODEL))

    def popup(**_: object) -> LabelDialogEntry:
        # The result lands while the user types the drawn shape's label.
        win._submit_ai_prompt(False)  # noqa: FBT003 -- the slot takes the Qt clicked flag positionally
        assert [s.label for s in canvas.shapes] == [None]
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
        held.append((self, job, _osam_worker._run(request, request.image)))

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
