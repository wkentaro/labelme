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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shapes", type=int, default=10)
    parser.add_argument("--vertices", type=int, default=10000)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--unique-labels", action="store_true")
    parser.add_argument("--cold-history", action="store_true")
    args = parser.parse_args()
    if min(args.shapes, args.vertices, args.samples) < 1:
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
        theta = np.linspace(0, 2 * np.pi, args.vertices, endpoint=False)
        points = np.column_stack((500 + 100 * np.cos(theta), 500 + 100 * np.sin(theta)))
        win._load_shapes(
            [
                Shape(
                    label=f"object-{i}" if args.unique_labels else "object",
                    points=points + i,
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
            if not args.cold_history:
                canvas.update()
                app.processEvents()
        canvas.update()
        app.processEvents()
        timings = []
        for step in range(args.samples):
            started = time.perf_counter()
            win.undo_shape_edit()
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
