from __future__ import annotations

from pathlib import Path
from typing import Literal

import osam.types._blob
import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from pytestqt.qtbot import QtBot

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata

# Smallest available model (~40MB) to keep download and inference fast
_AI_MODEL = "efficientsam:10m"


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
            Qt.NoModifier,
            4,
            None,
            id="polygon",
        ),
        pytest.param(
            "rectangle",
            [(0.25, 0.25)],
            (0.75, 0.75),
            Qt.NoModifier,
            2,
            None,
            id="rectangle",
        ),
        pytest.param(
            "oriented_rectangle",
            [(0.25, 0.5), (0.5, 0.5)],
            (0.5, 0.75),
            Qt.NoModifier,
            4,
            None,
            id="oriented_rectangle",
        ),
        pytest.param(
            "circle",
            [(0.5, 0.5)],
            (0.75, 0.5),
            Qt.NoModifier,
            2,
            None,
            id="circle",
        ),
        pytest.param(
            "line",
            [(0.25, 0.25)],
            (0.75, 0.75),
            Qt.NoModifier,
            2,
            None,
            id="line",
        ),
        pytest.param("point", [], (0.5, 0.5), Qt.NoModifier, 1, None, id="point"),
        pytest.param(
            "linestrip",
            [(0.25, 0.25), (0.5, 0.5)],
            (0.75, 0.75),
            Qt.ControlModifier,
            3,
            None,
            id="linestrip",
        ),
        pytest.param(
            "ai_points_to_shape",
            [],
            (0.5, 0.5),
            Qt.ControlModifier,
            None,
            "polygon",
            id="ai_points-polygon",
        ),
        pytest.param(
            "ai_points_to_shape",
            [],
            (0.5, 0.5),
            Qt.ControlModifier,
            2,
            "mask",
            id="ai_points-mask",
        ),
        pytest.param(
            "ai_box_to_shape",
            [(0.3, 0.3)],
            (0.7, 0.7),
            Qt.NoModifier,
            None,
            "polygon",
            id="ai_box-polygon",
        ),
        pytest.param(
            "ai_box_to_shape",
            [(0.3, 0.3)],
            (0.7, 0.7),
            Qt.NoModifier,
            2,
            "mask",
            id="ai_box-mask",
        ),
    ],
)
def test_annotate_shape_types(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    create_mode: str,
    setup_clicks: list[tuple[float, float]],
    finalize_click: tuple[float, float],
    finalize_modifier: Qt.KeyboardModifier,
    expected_num_points: int | None,
    ai_output_format: Literal["polygon", "mask"] | None,
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

    win._switch_canvas_mode(edit=False, createMode=create_mode)
    qtbot.wait(50)

    def click(
        xy: tuple[float, float], modifier: Qt.KeyboardModifier = Qt.NoModifier
    ) -> None:
        pos = to_pos(xy)
        qtbot.mouseMove(canvas, pos=pos)
        qtbot.wait(50)
        qtbot.mouseClick(canvas, Qt.LeftButton, modifier=modifier, pos=pos)
        qtbot.wait(50)

    for xy in setup_clicks:
        click(xy=xy)

    def enter_label_when_visible() -> None:
        if not win._label_dialog.isVisible():
            QTimer.singleShot(50, enter_label_when_visible)
            return
        qtbot.keyClicks(win._label_dialog.edit, label)
        qtbot.wait(50)
        qtbot.keyClick(win._label_dialog.edit, Qt.Key_Enter)

    QTimer.singleShot(0, enter_label_when_visible)

    click(xy=finalize_click, modifier=finalize_modifier)

    assert len(canvas.shapes) >= 1
    shape = canvas.shapes[0]
    assert shape.label == label
    assert shape.shape_type == expected_shape_type
    assert shape.group_id is None
    assert shape.flags == {}
    assert (shape.mask is not None) == (expected_shape_type == "mask")
    if expected_num_points is not None:
        assert len(shape.points) == expected_num_points

    win._save_label_file()
    assert_labelfile_sanity(out_file)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_ai_model_download(
    main_win: MainWinFactory,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    canvas.set_ai_model_name(_AI_MODEL)
    canvas.set_ai_output_format("polygon")

    win._switch_canvas_mode(edit=False, createMode="ai_box_to_shape")
    qtbot.wait(50)

    # Redirect osam blob storage to a temp directory so it thinks the model is not
    # downloaded. This exercises the download_ai_model dialog without touching the
    # real model cache in ~/.cache/osam.
    blob_base = str(tmp_path / "osam_blobs")

    def patched_path(self: osam.types._blob.Blob) -> str:
        if self.attachments:
            safe_hash = self.hash.replace("sha256:", "sha256-")
            return str(Path(blob_base) / safe_hash / self.filename)
        return str(Path(blob_base) / self.hash)

    monkeypatch.setattr(osam.types._blob.Blob, "path", property(patched_path))

    # Reset cached osam session so the fresh model is loaded from temp dir
    canvas._osam_session = None

    canvas_size = canvas.size()
    pos = QPoint(int(canvas_size.width() * 0.5), int(canvas_size.height() * 0.5))
    qtbot.mouseClick(canvas, Qt.LeftButton, pos=pos)

    # Verify the model was downloaded to the temp dir
    assert any(Path(blob_base).rglob("*"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
