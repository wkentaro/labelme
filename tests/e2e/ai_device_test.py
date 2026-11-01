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
    monkeypatch.setattr(Canvas, "ai_detect_job", property(lambda _: box["job"]))
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
        "Detecting 'sticky notes, pens'…",
        "Detecting 'sticky notes, pens' on CPU…",
        "Detecting…",
        "Detecting on CPU…",
        "Detecting 'dog'…",
        "",
    ]
    # Each detection, from text or an example box, is announced once.
    assert announced == [
        "Detecting 'sticky notes, pens'…",
        "Detecting…",
        "Detecting 'dog'…",
    ]


@pytest.mark.gui
def test_compute_device_setting_reaches_the_worker(*, main_win: MainWinFactory) -> None:
    win: MainWindow = main_win(config_overrides={"ai": {"device": "cpu"}})
    assert win._osam_worker._device == "cpu"

    win._apply_setting_change(("ai", "device"), "auto")

    assert win._osam_worker._device == "auto"
