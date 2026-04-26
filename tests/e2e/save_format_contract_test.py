from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Final

import numpy as np
import pytest
from PyQt5.QtCore import QTimer
from pytestqt.qtbot import QtBot

from labelme import utils
from labelme.app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import dismiss_active_modal
from .conftest import draw_and_commit_polygon
from .conftest import show_window_and_wait_for_imagedata

_RAW_FILE_NAME: Final[str] = "raw/2011_000003.jpg"
_DEFAULT_TRIANGLE: Final[tuple[tuple[float, float], ...]] = (
    (0.2, 0.2),
    (0.7, 0.2),
    (0.7, 0.7),
)


@pytest.mark.gui
@pytest.mark.parametrize("with_image_data", [True, False])
def test_save_image_data_field_matches_config(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    with_image_data: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE_NAME),
        config_overrides={"with_image_data": with_image_data},
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    draw_and_commit_polygon(
        qtbot=qtbot, win=win, label="cat", vertices=_DEFAULT_TRIANGLE
    )

    label_path = tmp_path / "2011_000003.json"
    win.save_labels(label_path=str(label_path))

    assert label_path.exists()
    with open(label_path) as f:
        data = json.load(f)
    if with_image_data:
        assert isinstance(data["imageData"], str) and data["imageData"]
        decoded = utils.img_b64_to_arr(data["imageData"])
        assert decoded.shape[0] == data["imageHeight"]
        assert decoded.shape[1] == data["imageWidth"]
    else:
        assert data["imageData"] is None
        assert (label_path.parent / data["imagePath"]).exists()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_round_trip_polygon_preserves_points(
    main_win: MainWinFactory,
    qtbot: QtBot,
    raw_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    label = "rt_polygon"
    label_path = tmp_path / "2011_000003.json"

    draw_and_commit_polygon(
        qtbot=qtbot, win=raw_win, label=label, vertices=_DEFAULT_TRIANGLE
    )

    saved_shape = next(
        s for s in raw_win._canvas_widgets.canvas.shapes if s.label == label
    )
    saved_points = [(p.x(), p.y()) for p in saved_shape.points]

    raw_win.save_labels(label_path=str(label_path))
    assert label_path.exists()
    raw_win.close()

    win2 = main_win(file_or_dir=str(label_path), output_dir=str(tmp_path))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win2)

    canvas2 = win2._canvas_widgets.canvas
    qtbot.waitUntil(
        lambda: any(s.label == label for s in canvas2.shapes), timeout=5_000
    )

    reopened = next(s for s in canvas2.shapes if s.label == label)
    reopened_points = [(p.x(), p.y()) for p in reopened.points]

    assert reopened.shape_type == "polygon"
    assert len(reopened_points) == len(saved_points)
    for (rx, ry), (sx, sy) in zip(reopened_points, saved_points, strict=True):
        assert abs(rx - sx) < 1.0
        assert abs(ry - sy) < 1.0

    close_or_pause(qtbot=qtbot, widget=win2, pause=pause)


@pytest.mark.gui
def test_round_trip_mask_shape_via_fixture(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    mask_arr = np.zeros((4, 4), dtype=np.uint8)
    mask_arr[1:3, 1:3] = 1
    mask_b64 = utils.img_arr_to_b64(mask_arr)

    raw_image_path = data_path / _RAW_FILE_NAME
    fixture_json = tmp_path / "mask_fixture.json"

    with open(raw_image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    fixture_data = {
        "version": "6.0.0",
        "flags": {},
        "shapes": [
            {
                "label": "mask_shape",
                "points": [[10.0, 10.0], [50.0, 50.0]],
                "group_id": None,
                "description": "",
                "shape_type": "mask",
                "flags": {},
                "mask": mask_b64,
            }
        ],
        "imagePath": "2011_000003.jpg",
        "imageData": img_b64,
        "imageHeight": 281,
        "imageWidth": 500,
    }
    with open(fixture_json, "w") as f:
        json.dump(fixture_data, f)

    # with_image_data=True so the re-saved JSON embeds the image and win2
    # does not need the original file alongside.
    win1 = main_win(
        file_or_dir=str(fixture_json),
        output_dir=str(tmp_path),
        config_overrides={"with_image_data": True},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win1)

    canvas1 = win1._canvas_widgets.canvas
    qtbot.waitUntil(
        lambda: any(s.label == "mask_shape" for s in canvas1.shapes), timeout=5_000
    )

    original_shape = next(s for s in canvas1.shapes if s.label == "mask_shape")
    assert original_shape.shape_type == "mask"
    assert original_shape.mask is not None

    resaved_path = tmp_path / "mask_resaved.json"
    win1.save_labels(label_path=str(resaved_path))
    assert resaved_path.exists()
    win1.close()

    win2 = main_win(file_or_dir=str(resaved_path), output_dir=str(tmp_path))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win2)

    canvas2 = win2._canvas_widgets.canvas
    qtbot.waitUntil(
        lambda: any(s.label == "mask_shape" for s in canvas2.shapes), timeout=5_000
    )

    reloaded = next(s for s in canvas2.shapes if s.label == "mask_shape")
    assert reloaded.shape_type == "mask"
    assert reloaded.mask is not None
    assert np.array_equal(reloaded.mask, original_shape.mask)

    close_or_pause(qtbot=qtbot, widget=win2, pause=pause)


@pytest.mark.gui
def test_open_json_with_missing_image_shows_error_and_recovers(
    qtbot: QtBot,
    raw_win: MainWindow,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    missing_image_json = tmp_path / "missing_image.json"
    json_data = {
        "version": "6.0.0",
        "flags": {},
        "shapes": [],
        "imagePath": "does_not_exist.jpg",
        "imageData": None,
        "imageHeight": 100,
        "imageWidth": 100,
    }
    with open(missing_image_json, "w") as f:
        json.dump(json_data, f)

    QTimer.singleShot(0, lambda: dismiss_active_modal(qtbot=qtbot))
    raw_win._load_file(str(missing_image_json))

    raw_win._load_file(str(data_path / _RAW_FILE_NAME))
    qtbot.waitUntil(lambda: raw_win._image_data is not None, timeout=5_000)

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_title_returns_to_clean_after_save(
    monkeypatch: pytest.MonkeyPatch,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE_NAME),
        config_overrides={"auto_save": False},
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    draw_and_commit_polygon(
        qtbot=qtbot, win=win, label="cat", vertices=_DEFAULT_TRIANGLE
    )
    assert win.windowTitle().endswith("*")

    label_path = tmp_path / "2011_000003.json"
    monkeypatch.setattr(win, "prompt_save_file_path", lambda: str(label_path))
    win._save_label_file()

    assert label_path.exists()
    assert not win.windowTitle().endswith("*")

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
