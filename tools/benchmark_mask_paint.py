"""Run with QT_QPA_PLATFORM=offscreen python -m tools.benchmark_mask_paint."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final
from unittest.mock import patch

import numpy as np
import skimage.measure
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme._app import MainWindow
from labelme._shape import Shape

WINDOW_WIDTH: Final[int] = 1400
WINDOW_HEIGHT: Final[int] = 1000
CONTOUR_PAD: Final[int] = 1
FILL_RGBA: Final[tuple[int, int, int, int]] = (0, 255, 0, 128)
PERCENTILE: Final[int] = 95
MS_PER_S: Final[int] = 1000


def _time_ms(*, func: Callable[[], None], samples: int) -> dict[str, float]:
    timings = []
    for _ in range(samples):
        started = time.perf_counter()
        func()
        timings.append((time.perf_counter() - started) * MS_PER_S)
    return {
        "p50_ms": statistics.median(timings),
        "p95_ms": float(np.percentile(timings, PERCENTILE)),
        "min_ms": min(timings),
        "max_ms": max(timings),
    }


def _disc(*, size: int) -> np.ndarray:
    ys, xs = np.mgrid[:size, :size]
    center = (size - 1) / 2
    return (xs - center) ** 2 + (ys - center) ** 2 <= (size / 2 - 1) ** 2


# The two blocks below replicate the fill and contour halves of
# labelme/_widgets/_shape_render.py:_paint_mask, so each can be timed alone.
def _fill_block(*, painter: QtGui.QPainter, mask: np.ndarray) -> None:
    rgba = np.zeros(mask.shape + (4,), dtype=np.uint8)
    rgba[mask] = FILL_RGBA
    height, width = mask.shape
    bitmap = QtGui.QImage(
        rgba.data, width, height, 4 * width, QtGui.QImage.Format.Format_RGBA8888
    )
    painter.drawImage(QtCore.QRectF(0, 0, width, height), bitmap)


def _contour_block(*, painter: QtGui.QPainter, mask: np.ndarray) -> None:
    contour_path = QtGui.QPainterPath()
    for contour in skimage.measure.find_contours(np.pad(mask, pad_width=CONTOUR_PAD)):
        xy = contour[:, ::-1] - CONTOUR_PAD
        contour_path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in xy]))
    painter.drawPath(contour_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--masks", type=int, default=50)
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--image", type=int, default=2000)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args()
    if min(args.masks, args.size, args.image, args.samples) < 1:
        parser.error("counts must be positive")
    if args.size > args.image:
        parser.error("--size must not exceed --image")
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = root / "config.yaml"
        config.write_text("{}")
        image = QtGui.QImage(args.image, args.image, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        image.save(str(root / "image.png"))
        settings = QtCore.QSettings(
            str(root / "settings.ini"), QtCore.QSettings.Format.IniFormat
        )
        with patch.object(QtCore, "QSettings", return_value=settings):
            win = MainWindow(
                config_file=config,
                config_overrides={"auto_save": False},
                file_or_dir=str(root / "image.png"),
                output_dir=str(root),
            )
        win.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        win.show()
        app.processEvents()
        mask = _disc(size=args.size)
        # Spread masks over a grid covering the image.
        span = args.image - args.size
        columns = max(int(np.ceil(np.sqrt(args.masks))), 1)
        step = span / max(columns - 1, 1)
        shapes = []
        for i in range(args.masks):
            x = int(i % columns * step)
            y = int(i // columns * step)
            shapes.append(
                Shape(
                    label=f"mask-{i}",
                    shape_type="mask",
                    points=np.array(
                        [[x, y], [x + args.size - 1, y + args.size - 1]], dtype=float
                    ),
                    mask=mask.copy(),
                )
            )
        win._load_shapes(shapes=shapes, replace=True)
        win.set_fit_window_mode()
        app.processEvents()
        canvas = win._canvas_widgets.canvas
        assert len(canvas.shapes) == args.masks
        repaint = _time_ms(func=canvas.repaint, samples=args.samples)

        target = QtGui.QImage(
            args.size, args.size, QtGui.QImage.Format.Format_ARGB32_Premultiplied
        )
        painter = QtGui.QPainter(target)
        fill = _time_ms(
            func=lambda: _fill_block(painter=painter, mask=mask),
            samples=args.samples,
        )
        contour = _time_ms(
            func=lambda: _contour_block(painter=painter, mask=mask),
            samples=args.samples,
        )
        painter.end()
        print(
            json.dumps(
                {
                    **vars(args),
                    "qt": QtCore.qVersion(),
                    "scale": canvas.scale,
                    "full_repaint": repaint,
                    "fill_block_one_mask": fill,
                    "contour_block_one_mask": contour,
                }
            )
        )
        win.mark_clean()
        win.close()


if __name__ == "__main__":
    main()
