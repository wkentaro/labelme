from __future__ import annotations

import pytest

from labelme._app import MainWindow
from labelme._automation import OsamWorker

from .conftest import MainWinFactory


@pytest.mark.gui
def test_status_bar_shows_where_ai_runs(
    *, main_win: MainWinFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    win: MainWindow = main_win()
    state: dict[str, object] = {"busy": False, "device": None}
    monkeypatch.setattr(OsamWorker, "busy", property(lambda _: state["busy"]))
    monkeypatch.setattr(OsamWorker, "device", property(lambda _: state["device"]))
    label = win._status_bar.ai

    texts = []
    for busy, device in [(True, None), (True, "webgpu"), (True, "cpu"), (False, None)]:
        state.update(busy=busy, device=device)
        win._osam_worker.activity_changed.emit()
        texts.append(label.text())

    assert texts == ["Running AI…", "Running AI…", "Running AI on CPU…", ""]


@pytest.mark.gui
def test_compute_device_setting_reaches_the_worker(*, main_win: MainWinFactory) -> None:
    win: MainWindow = main_win(config_overrides={"ai": {"device": "cpu"}})
    assert win._osam_worker._device == "cpu"

    win._apply_setting_change(("ai", "device"), "auto")

    assert win._osam_worker._device == "auto"
