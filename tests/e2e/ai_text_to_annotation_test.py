from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import numpy as np
import osam.types
import pytest
from pytestqt.qtbot import QtBot

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata

if TYPE_CHECKING:
    from labelme.app import MainWindow

_AI_TEXT_MODEL = "yoloworld:latest"


def _make_response(
    texts: list[str],
    boxes: list[tuple[int, int, int, int]],
    scores: list[float],
    label_indices: list[int],
    with_masks: bool = False,
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
    texts: list[str], with_masks: bool = False
) -> osam.types.GenerateResponse:
    person_idx = texts.index("person")
    return _make_response(
        texts=texts,
        boxes=[(50, 30, 200, 300), (220, 40, 350, 290)],
        scores=[0.85, 0.45],
        label_indices=[person_idx, person_idx],
        with_masks=with_masks,
    )


def _make_multi_label_response(texts: list[str]) -> osam.types.GenerateResponse:
    person_idx = texts.index("person")
    sofa_idx = texts.index("sofa")
    return _make_response(
        texts=texts,
        boxes=[(50, 30, 200, 300), (10, 150, 400, 330)],
        scores=[0.85, 0.70],
        label_indices=[person_idx, sofa_idx],
    )


def _install_mock_session(
    win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    response_fn: Callable[..., osam.types.GenerateResponse],
) -> None:
    class _FakeModelType:
        @staticmethod
        def get_size() -> int:
            return 1

    monkeypatch.setattr("osam.apis.get_model_type_by_name", lambda name: _FakeModelType)

    mock_session = MagicMock()
    mock_session.model_name = _AI_TEXT_MODEL
    mock_session.run = MagicMock(
        side_effect=lambda **kw: response_fn(texts=kw["texts"])
    )
    win._text_osam_session = mock_session


def _run_text_prompt(
    *,
    win: MainWindow,
    qtbot: QtBot,
    text: str,
    create_mode: str,
    score_threshold: float = 0.1,
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

    win._submit_ai_prompt(False)
    qtbot.wait(100)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("create_mode", "expected_shape_type", "text", "response_fn", "expected_labels"),
    [
        pytest.param(
            "rectangle",
            "rectangle",
            "person",
            _make_person_response,
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
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    create_mode: str,
    expected_shape_type: str,
    text: str,
    response_fn: Callable[..., osam.types.GenerateResponse],
    expected_labels: set[str],
) -> None:
    input_file = str(data_path / "raw/2011_000003.jpg")
    win = main_win(
        file_or_dir=input_file,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    assert len(canvas.shapes) == 0

    if create_mode == "ai_box_to_shape":
        canvas.set_ai_model_name(_AI_TEXT_MODEL)
        canvas.set_ai_output_format("polygon")

    _install_mock_session(win=win, monkeypatch=monkeypatch, response_fn=response_fn)
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
        assert shape.shape_type == expected_shape_type

    out_file = str(tmp_path / "2011_000003.json")
    win._save_label_file()
    assert_labelfile_sanity(out_file)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_nms_deduplicates_existing_shapes(
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
        win=win, monkeypatch=monkeypatch, response_fn=_make_person_response
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
        win=win, monkeypatch=monkeypatch, response_fn=_make_person_response
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
def test_text_prompt_inference_error_surfaces_without_crashing(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    # A model error during text-to-annotation inference must not crash the app:
    # it surfaces as a non-fatal status message and the window stays alive.
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas

    def _raise(**_: object) -> osam.types.GenerateResponse:
        raise RuntimeError("boom")

    _install_mock_session(win=win, monkeypatch=monkeypatch, response_fn=_raise)
    _run_text_prompt(win=win, qtbot=qtbot, text="person", create_mode="rectangle")

    assert win.isVisible()
    assert canvas.shapes == []
    assert "AI inference failed" in win.statusBar().currentMessage()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_canvas_inference_failed_signal_surfaces_status_message(
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
