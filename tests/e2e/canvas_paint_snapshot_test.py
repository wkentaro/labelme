from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import QRect
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QPainter
from PyQt5.QtGui import QRegion
from PyQt5.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.widgets.canvas import Canvas

from ..conftest import close_or_pause
from .conftest import click_canvas_fraction
from .conftest import draw_and_commit_polygon
from .conftest import image_to_widget_pos
from .conftest import select_shape

# Pinning canvas size + scale + background decouples the snapshot from
# platform window chrome (toolbar/dock metrics) so the rendered pixels are
# determined by Qt's raster engine, which is deterministic across platforms
# for non-text geometry. The Fusion style is set by labelme.__main__.main(),
# which the main_win fixture invokes for every test.
_RENDER_WIDTH: Final[int] = 600
_RENDER_HEIGHT: Final[int] = 450
_RENDER_SCALE: Final[float] = 1.0
_BACKGROUND_COLOR: Final[QColor] = QColor(232, 232, 232)
_PAINT_SETTLE_MS: Final[int] = 100
_MODE_SWITCH_SETTLE_MS: Final[int] = 50

_TRIANGLE_FRACTIONS: Final[tuple[tuple[float, float], ...]] = (
    (0.2, 0.2),
    (0.6, 0.2),
    (0.6, 0.5),
)


def _pin_canvas_for_snapshot(qtbot: QtBot, canvas: Canvas) -> None:
    canvas.setFixedSize(_RENDER_WIDTH, _RENDER_HEIGHT)
    canvas.scale = _RENDER_SCALE
    canvas.update()
    qtbot.wait(_PAINT_SETTLE_MS)


def _render_canvas_offscreen(canvas: Canvas) -> QImage:
    image = QImage(_RENDER_WIDTH, _RENDER_HEIGHT, QImage.Format_ARGB32)
    image.fill(_BACKGROUND_COLOR)
    painter = QPainter(image)
    try:
        # DrawChildren only — skip DrawWindowBackground so the platform palette
        # does not leak into the letterbox; our pre-fill provides the bg color.
        canvas.render(
            painter,
            QPoint(0, 0),
            QRegion(QRect(0, 0, _RENDER_WIDTH, _RENDER_HEIGHT)),
            QWidget.DrawChildren,
        )
    finally:
        painter.end()
    return image


def _qimage_to_numpy(image: QImage) -> np.ndarray:
    assert image.format() == QImage.Format_ARGB32
    width = image.width()
    height = image.height()
    bytes_per_line = image.bytesPerLine()
    ptr = image.bits()
    raw_bytes = ptr.asstring(bytes_per_line * height)
    arr = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(
        (height, bytes_per_line // 4, 4)
    )
    return arr[:, :width, :].copy()


def _save_snapshot(path: Path, image: QImage) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))


def _assert_matches_snapshot(actual: QImage, snapshot_path: Path) -> None:
    TOLERANCE_MAX_DIFF: Final[int] = 1
    TOLERANCE_PASSING_FRACTION: Final[float] = 0.995
    if not snapshot_path.exists():
        pytest.fail(
            f"Snapshot not found: {snapshot_path}\n"
            "Run with --update-snapshots to generate it."
        )
    actual_arr = _qimage_to_numpy(actual)
    snapshot_qimage = QImage(str(snapshot_path)).convertToFormat(QImage.Format_ARGB32)
    assert not snapshot_qimage.isNull(), f"Failed to load snapshot PNG: {snapshot_path}"
    snapshot_arr = _qimage_to_numpy(snapshot_qimage)
    assert actual_arr.shape == snapshot_arr.shape, (
        f"Canvas size changed: actual={actual_arr.shape}, snapshot={snapshot_arr.shape}"
    )
    diff = np.abs(actual_arr.astype(np.int32) - snapshot_arr.astype(np.int32))
    pixel_pass = (diff <= TOLERANCE_MAX_DIFF).all(axis=2)
    fraction = float(pixel_pass.mean())
    assert fraction >= TOLERANCE_PASSING_FRACTION, (
        f"Too many pixels differ: {fraction:.4%} pass "
        f"(need >= {TOLERANCE_PASSING_FRACTION:.1%}), "
        f"max per-channel diff={int(diff.max())}"
    )


def _check_or_update_snapshot(
    canvas: Canvas,
    snapshot_path: Path,
    update_snapshots: bool,
) -> None:
    actual = _render_canvas_offscreen(canvas=canvas)
    if update_snapshots:
        _save_snapshot(path=snapshot_path, image=actual)
    else:
        _assert_matches_snapshot(actual=actual, snapshot_path=snapshot_path)


@pytest.mark.gui
def test_snapshot_empty_canvas(
    qtbot: QtBot,
    raw_win: MainWindow,
    snapshot_dir: Path,
    update_snapshots: bool,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    assert len(canvas.shapes) == 0
    _pin_canvas_for_snapshot(qtbot=qtbot, canvas=canvas)

    _check_or_update_snapshot(
        canvas=canvas,
        snapshot_path=snapshot_dir / "canvas/empty_canvas.png",
        update_snapshots=update_snapshots,
    )

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_snapshot_shapes_unselected(
    qtbot: QtBot,
    annotated_win: MainWindow,
    snapshot_dir: Path,
    update_snapshots: bool,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    assert len(canvas.shapes) > 0
    assert len(canvas.selected_shapes) == 0
    _pin_canvas_for_snapshot(qtbot=qtbot, canvas=canvas)

    _check_or_update_snapshot(
        canvas=canvas,
        snapshot_path=snapshot_dir / "canvas/shapes_unselected.png",
        update_snapshots=update_snapshots,
    )

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_snapshot_one_polygon_selected(
    qtbot: QtBot,
    annotated_win: MainWindow,
    snapshot_dir: Path,
    update_snapshots: bool,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    assert len(canvas.shapes) > 0
    _pin_canvas_for_snapshot(qtbot=qtbot, canvas=canvas)

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.wait(_PAINT_SETTLE_MS)

    _check_or_update_snapshot(
        canvas=canvas,
        snapshot_path=snapshot_dir / "canvas/one_polygon_selected.png",
        update_snapshots=update_snapshots,
    )

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_snapshot_polygon_mid_draw(
    qtbot: QtBot,
    raw_win: MainWindow,
    snapshot_dir: Path,
    update_snapshots: bool,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    pixmap = canvas.pixmap
    assert pixmap is not None
    _pin_canvas_for_snapshot(qtbot=qtbot, canvas=canvas)

    raw_win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(_MODE_SWITCH_SETTLE_MS)

    for xy in _TRIANGLE_FRACTIONS[:2]:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None
    assert len(canvas.current.points) == 2

    fx, fy = _TRIANGLE_FRACTIONS[2]
    cursor_image_pos = QPointF(pixmap.width() * fx, pixmap.height() * fy)
    cursor_pos = image_to_widget_pos(canvas=canvas, image_pos=cursor_image_pos)
    qtbot.mouseMove(canvas, pos=cursor_pos)
    qtbot.wait(_PAINT_SETTLE_MS)

    _check_or_update_snapshot(
        canvas=canvas,
        snapshot_path=snapshot_dir / "canvas/polygon_mid_draw.png",
        update_snapshots=update_snapshots,
    )

    # Cancel the in-progress shape; without this close_or_pause triggers a dialog.
    qtbot.keyPress(canvas, Qt.Key_Escape)
    qtbot.wait(_MODE_SWITCH_SETTLE_MS)
    assert canvas.current is None

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_snapshot_after_polygon_commit(
    qtbot: QtBot,
    raw_win: MainWindow,
    snapshot_dir: Path,
    update_snapshots: bool,
    pause: bool,
) -> None:
    # Regression: after committing a polygon the snap-highlighted last vertex
    # must be cleared from the paint surface.
    canvas = raw_win._canvas_widgets.canvas
    assert len(canvas.shapes) == 0
    _pin_canvas_for_snapshot(qtbot=qtbot, canvas=canvas)

    draw_and_commit_polygon(
        qtbot=qtbot,
        win=raw_win,
        label="snap_clear",
        vertices=_TRIANGLE_FRACTIONS,
    )
    assert len(canvas.shapes) == 1
    assert canvas.current is None
    qtbot.wait(_PAINT_SETTLE_MS)

    _check_or_update_snapshot(
        canvas=canvas,
        snapshot_path=snapshot_dir / "canvas/after_polygon_commit.png",
        update_snapshots=update_snapshots,
    )

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_snapshot_hide_background_shapes(
    qtbot: QtBot,
    annotated_win: MainWindow,
    snapshot_dir: Path,
    update_snapshots: bool,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    assert len(canvas.shapes) > 1
    _pin_canvas_for_snapshot(qtbot=qtbot, canvas=canvas)

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)

    canvas.hide_background_shapes(value=True)
    qtbot.wait(_PAINT_SETTLE_MS)

    _check_or_update_snapshot(
        canvas=canvas,
        snapshot_path=snapshot_dir / "canvas/hide_background_shapes.png",
        update_snapshots=update_snapshots,
    )

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
