"""Run with QT_QPA_PLATFORM=offscreen python -m tools.benchmark_undo."""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme._app import MainWindow
from labelme._shape import Shape
from labelme._widgets._canvas import _Hover
from labelme._widgets._shape_render import ShapeRenderCache


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shapes", type=int, default=1)
    parser.add_argument("--vertices", type=int, default=10000)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--labels", type=int, default=5)
    parser.add_argument(
        "--active", choices=["idle", "selected", "hovered", "all"], default="idle"
    )
    parser.add_argument("--cache-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--cold-cache", action="store_true")
    args = parser.parse_args()
    if args.cache_bytes < 0:
        parser.error("--cache-bytes must be nonnegative")
    if min(args.shapes, args.vertices, args.samples, args.labels) < 1:
        parser.error("counts must be positive")
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = root / "config.yaml"
        config.write_text("{}")
        image = QtGui.QImage(1000, 1000, QtGui.QImage.Format.Format_RGB32)
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
        canvas = win._canvas_widgets.canvas
        canvas._render_cache = ShapeRenderCache(max_bytes=args.cache_bytes)
        theta = np.linspace(0, 2 * np.pi, args.vertices, endpoint=False)
        points = np.column_stack((50 + 40 * np.cos(theta), 50 + 40 * np.sin(theta)))
        win._load_shapes(
            shapes=[
                Shape(
                    label=f"object-{i % args.labels}",
                    points=points + [i % 10 * 90, i // 10 * 90],
                    closed=True,
                )
                for i in range(args.shapes)
            ],
            replace=True,
        )
        canvas.setParent(None)
        canvas.setFixedSize(1000, 1000)
        canvas.scale = 1
        canvas.show()
        app.processEvents()
        canvas.shape_backups = collections.deque(maxlen=args.samples + 2)
        canvas.backup_shapes()
        for _ in range(args.samples):
            canvas.shapes[0].points[0, 0] += 1
            canvas.backup_shapes()
        canvas.update()
        app.processEvents()
        timings = []
        for step in range(args.samples):
            if args.cold_cache:
                canvas._render_cache.clear()
            started = time.perf_counter()
            win.undo_shape_edit()
            if args.active in ("selected", "all"):
                canvas.selected_shapes = (
                    canvas.shapes if args.active == "all" else canvas.shapes[:1]
                )
            elif args.active == "hovered":
                canvas._hover = _Hover(shape=canvas.shapes[0])
            app.processEvents()
            timings.append((time.perf_counter() - started) * 1000)
            assert canvas.shapes[0].points[0, 0] == (
                points[0, 0] + args.samples - step - 1
            )
        print(
            json.dumps(
                {
                    **vars(args),
                    "qt": QtCore.qVersion(),
                    "cache_estimated_bytes": canvas._render_cache._size_bytes,
                    "p50_ms": statistics.median(timings),
                    "p95_ms": float(np.percentile(timings, 95)),
                    "samples_ms": timings,
                }
            )
        )
        canvas.close()
        win.mark_clean()
        win.close()


if __name__ == "__main__":
    main()
