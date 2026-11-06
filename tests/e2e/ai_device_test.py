from __future__ import annotations

from types import SimpleNamespace

import pytest
from pytestqt.qtbot import QtBot

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
    # Each distinct task/device status is announced, never a timer tick.
    assert announced == [
        "Segmenting…",
        "Segmenting on CPU…",
        "Finding all 'sticky notes, pens'…",
        "Finding all 'sticky notes, pens' on CPU…",
        "Finding matches…",
        "Finding matches on CPU…",
        "Finding all 'dog'…",
    ]


@pytest.mark.gui
def test_compute_device_setting_reaches_the_worker(*, main_win: MainWinFactory) -> None:
    win: MainWindow = main_win(config_overrides={"ai": {"device": "cpu"}})
    assert win._osam_worker._device == "cpu"

    win._apply_setting_change(("ai", "device"), "auto")

    assert win._osam_worker._device == "auto"


@pytest.mark.gui
def test_stage_text_and_elapsed_time_without_repeated_announcements(
    *, main_win: MainWinFactory, monkeypatch: pytest.MonkeyPatch, qtbot: QtBot
) -> None:
    win = main_win()
    state: dict[str, object] = {
        "job": object(),
        "stage": "starting",
        "model_name": "sam3:latest",
        "device": None,
        "elapsed_s": 0.0,
    }
    for name in state:
        monkeypatch.setattr(OsamWorker, name, property(lambda _, key=name: state[key]))
    announced: list[str] = []
    monkeypatch.setattr(win, "_announce", announced.append)
    worker = win._osam_worker
    label = win._status_bar.ai

    worker.activity_changed.emit()
    assert label.text() == "Starting AI…"
    state["stage"] = "loading"
    worker.activity_changed.emit()
    assert label.text() == "Loading SAM 3…"

    state.update(stage="encoding", device="cpu", elapsed_s=2.0)
    worker.activity_changed.emit()
    assert label.text() == "Preparing image on CPU…"
    state["elapsed_s"] = 4.0
    qtbot.waitUntil(
        lambda: label.text() == "Preparing image on CPU… · 4 s", timeout=2000
    )
    assert announced == ["Starting AI…", "Loading SAM 3…", "Preparing image on CPU…"]

    state["stage"] = "generating"
    worker.activity_changed.emit()
    assert label.text() == "Segmenting on CPU… · 4 s"
    assert announced[-1] == "Segmenting on CPU…"

    state.update(job=None, stage=None, device=None, elapsed_s=0.0)
    worker.activity_changed.emit()
    assert label.text() == ""
    assert not win._ai_status_timer.isActive()
