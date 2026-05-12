from __future__ import annotations

import numpy as np
from PyQt5 import QtCore

from labelme._automation import Detection
from labelme._automation._bbox import suppress_detections_overlapping_existing_shapes
from labelme._shape import Shape


def test_suppress_drops_polygon_detection_overlapping_existing_polygon() -> None:
    existing = Shape(shape_type="polygon")
    for x, y in [(0, 0), (10, 0), (10, 10), (0, 10)]:
        existing.add_point(QtCore.QPointF(x, y))

    detection_mask = np.ones((11, 11), dtype=bool)
    detection = Detection(bbox=(0.0, 0.0, 10.0, 10.0), mask=detection_mask)

    kept = suppress_detections_overlapping_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert kept == []


def test_suppress_keeps_when_iou_below_threshold() -> None:
    existing = Shape(shape_type="rectangle")
    existing.add_point(QtCore.QPointF(0, 0))
    existing.add_point(QtCore.QPointF(10, 10))

    detection = Detection(bbox=(8.0, 8.0, 18.0, 18.0))

    kept = suppress_detections_overlapping_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert kept == [detection]


def test_suppress_uses_mask_iou_not_bbox_iou() -> None:
    # Two right triangles share the same bbox but cover opposite halves,
    # so bbox IoU would be 1.0 while mask IoU is 0.
    existing = Shape(shape_type="polygon")
    for x, y in [(0, 0), (10, 0), (0, 10)]:
        existing.add_point(QtCore.QPointF(x, y))

    rows, cols = np.indices((11, 11))
    detection_mask = rows + cols > 10
    detection = Detection(bbox=(0.0, 0.0, 10.0, 10.0), mask=detection_mask)

    kept = suppress_detections_overlapping_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert kept == [detection]
