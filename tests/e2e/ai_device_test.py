from __future__ import annotations

import pytest

from labelme._app import MainWindow
from labelme._app import _AiTextJob
from labelme._automation import OsamWorker

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
    state: dict[str, object] = {"job": None, "device": None}
    monkeypatch.setattr(OsamWorker, "job", property(lambda _: state["job"]))
    monkeypatch.setattr(OsamWorker, "device", property(lambda _: state["device"]))
    label = win._status_bar.ai

    texts = []
    for job, device in [
        (object(), None),
        (object(), "cpu"),
        (text_job, "webgpu"),
        (text_job, "cpu"),
        (None, None),
    ]:
        state.update(job=job, device=device)
        win._osam_worker.activity_changed.emit()
        texts.append(label.text())

    assert texts == [
        "Segmenting…",
        "Segmenting on CPU…",
        "Detecting 'sticky notes, pens'…",
        "Detecting 'sticky notes, pens' on CPU…",
        "",
    ]


@pytest.mark.gui
def test_compute_device_setting_reaches_the_worker(*, main_win: MainWinFactory) -> None:
    win: MainWindow = main_win(config_overrides={"ai": {"device": "cpu"}})
    assert win._osam_worker._device == "cpu"

    win._apply_setting_change(("ai", "device"), "auto")

    assert win._osam_worker._device == "auto"
