from __future__ import annotations

from types import SimpleNamespace

import pytest

from labelme._app import MainWindow
from labelme._app import _AiTextJob
from labelme._automation import OsamWorker
from labelme._widgets._canvas import Canvas

from .conftest import MainWinFactory


@pytest.mark.gui
def test_status_bar_names_the_running_ai_task(
    *, main_win: MainWinFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    win: MainWindow = main_win()
    text_job = _AiTextJob(
        pixmap_key=0,
        texts=["sticky notes", " pens"],
        shape_type="rectangle",
        iou_threshold=0.5,
        score_threshold=0.1,
        image_size=None,
    )
    box_job = SimpleNamespace(query="")
    dog_box_job = SimpleNamespace(query="dog")
    box: dict[str, object] = {"job": box_job}
    state: dict[str, object] = {"job": None, "device": None}
    monkeypatch.setattr(OsamWorker, "job", property(lambda _: state["job"]))
    monkeypatch.setattr(OsamWorker, "device", property(lambda _: state["device"]))
    monkeypatch.setattr(Canvas, "ai_find_all_job", property(lambda _: box["job"]))
    announced: list[str] = []
    monkeypatch.setattr(win, "_announce", announced.append)
    label = win._status_bar.ai

    texts = []
    for job, device in [
        (object(), None),
        (object(), "cpu"),
        (text_job, "webgpu"),
        (text_job, "cpu"),
        (box_job, None),
        (box_job, "cpu"),
        (dog_box_job, None),
        (None, None),
    ]:
        if job is dog_box_job:
            box["job"] = job
        state.update(job=job, device=device)
        win._osam_worker.activity_changed.emit()
        texts.append(label.text())

    assert texts == [
        "Segmenting…",
        "Segmenting on CPU…",
        "Finding all 'sticky notes, pens'…",
        "Finding all 'sticky notes, pens' on CPU…",
        "Finding matches…",
        "Finding matches on CPU…",
        "Finding all 'dog'…",
        "",
    ]
    # Each detection, from text or an example box, is announced once.
    assert announced == [
        "Finding all 'sticky notes, pens'…",
        "Finding matches…",
        "Finding all 'dog'…",
    ]


@pytest.mark.gui
def test_compute_device_setting_reaches_the_worker(*, main_win: MainWinFactory) -> None:
    win: MainWindow = main_win(config_overrides={"ai": {"device": "cpu"}})
    assert win._osam_worker._device == "cpu"

    win._apply_setting_change(("ai", "device"), "auto")

    assert win._osam_worker._device == "auto"


@pytest.mark.gui
def test_status_bar_names_the_stage_and_time_of_a_slow_prompt(
    *, main_win: MainWinFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    win: MainWindow = main_win()
    text_job = _AiTextJob(
        pixmap_key=0,
        texts=["dog"],
        shape_type="rectangle",
        iou_threshold=0.5,
        score_threshold=0.1,
        image_size=None,
    )
    win._ai_text_job = text_job
    state: dict[str, object] = {}
    for name in ["job", "stage", "device", "model_name"]:
        monkeypatch.setattr(
            OsamWorker, name, property(lambda _, name=name: state.get(name))
        )
    monkeypatch.setattr(Canvas, "ai_find_all_job", property(lambda _: None))
    announced: list[str] = []
    monkeypatch.setattr(win, "_announce", announced.append)
    label = win._status_bar.ai

    def show(**changes: object) -> str:
        state.update(changes)
        win._osam_worker.activity_changed.emit()
        return label.text()

    segment = object()
    assert show(job=segment, stage="starting") == "Starting AI…"
    assert show(stage="loading", model_name="sam2:latest") == "Loading SAM 2 Base+…"
    assert show(stage="encoding", device="cpu") == "Preparing image on CPU…"
    assert show(stage="generating") == "Segmenting on CPU…"
    # A warm Segment, such as each preview while the cursor moves, is silent.
    for _ in range(3):
        assert show(job=object(), stage=None) == "Segmenting on CPU…"
    assert announced == [
        "Starting AI…",
        "Loading SAM 2 Base+…",
        "Preparing image on CPU…",
    ]

    announced.clear()
    assert show(job=text_job, stage="encoding", device=None) == "Preparing image…"
    win._ai_status_started_at -= 4  # as if 4 seconds have passed
    assert show(stage="generating") == "Finding all 'dog'… · 4 s"
    assert show() == "Finding all 'dog'… · 4 s"  # a tick
    # A retry on CPU keeps the job's clock.
    assert show(job=None, stage=None) == ""
    assert not win._ai_status_timer.isActive()
    assert show(job=text_job, stage="starting") == "Starting AI… · 4 s"
    assert announced == ["Preparing image…", "Finding all 'dog'…", "Starting AI…"]
