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
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme._app import MainWindow
from labelme._shape import Shape
from labelme._widgets._shape_render import ShapeRenderCache

WINDOW_WIDTH: Final[int] = 1400
WINDOW_HEIGHT: Final[int] = 1000
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--masks", type=int, default=50)
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--image", type=int, default=2000)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--cache-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args()
    if args.cache_bytes < 0:
        parser.error("--cache-bytes must be nonnegative")
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
        # Spread masks over a grid covering the image.
        span = args.image - args.size
        columns = max(int(np.ceil(np.sqrt(args.masks))), 1)
        step = span / max(columns - 1, 1)
        shapes = []
        for i in range(args.masks):
            x = int(i % columns * step)
            y = int(i // columns * step)
            mask = _disc(size=args.size)
            # Distinct masks prevent shared content from hiding cache pressure.
            hole = max(args.size // 20, 1)
            offset = args.size // 4 + i % max(args.size // 2, 1)
            mask[offset : offset + hole, args.size // 2 : args.size // 2 + hole] = False
            shapes.append(
                Shape(
                    label=f"mask-{i}",
                    shape_type="mask",
                    points=np.array(
                        [[x, y], [x + args.size - 1, y + args.size - 1]], dtype=float
                    ),
                    mask=mask,
                )
            )
        win._load_shapes(shapes=shapes, replace=True)
        win.set_fit_window_mode()
        app.processEvents()
        canvas = win._canvas_widgets.canvas
        assert len(canvas.shapes) == args.masks
        canvas._render_cache = ShapeRenderCache(max_bytes=args.cache_bytes)
        canvas.repaint()
        repaint = _time_ms(func=canvas.repaint, samples=args.samples)
        retained_bytes = canvas._render_cache._size_bytes

        def cold_repaint() -> None:
            canvas._render_cache.clear()
            canvas.repaint()

        cold = _time_ms(func=cold_repaint, samples=args.samples)
        print(
            json.dumps(
                {
                    **vars(args),
                    "qt": QtCore.qVersion(),
                    "scale": canvas.scale,
                    "full_repaint": repaint,
                    "cold_repaint": cold,
                    "cache_estimated_bytes": retained_bytes,
                }
            )
        )
        win.mark_clean()
        win.close()


if __name__ == "__main__":
    main()
