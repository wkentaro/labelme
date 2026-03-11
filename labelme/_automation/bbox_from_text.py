import json
import time
from typing import Literal

import numpy as np
import osam
from loguru import logger
from numpy.typing import NDArray
from PyQt5 import QtCore

from labelme.shape import Shape

from ._osam_session import OsamSession
from .polygon_from_mask import compute_polygon_from_mask


def get_bboxes_from_texts(
    session: OsamSession, image: np.ndarray, image_id: str, texts: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
    logger.debug(
        f"Requesting with model={session.model_name!r}, "
        f"image={(image.shape, image.dtype)}, texts={texts!r}"
    )
    t_start: float = time.time()
    response: osam.types.GenerateResponse = session.run(
        image=image,
        image_id=image_id,
        texts=texts,
    )

    num_annotations: int = len(response.annotations)
    logger.debug(
        f"Response: num_annotations={num_annotations}, "
        f"elapsed_time={time.time() - t_start:.3f} [s]"
    )

    boxes: NDArray[np.float32] = np.empty((num_annotations, 4), dtype=np.float32)
    scores: NDArray[np.float32] = np.empty((num_annotations,), dtype=np.float32)
    labels: NDArray[np.int32] = np.empty((num_annotations,), dtype=np.int32)
    for i, annotation in enumerate(response.annotations):
        if annotation.bounding_box is None:
            raise ValueError("Bounding box is missing in the annotation.")
        if annotation.text not in texts:
            raise ValueError(
                f"Unexpected text {annotation.text!r} found in the response."
            )
        boxes[i] = [
            annotation.bounding_box.xmin,
            annotation.bounding_box.ymin,
            annotation.bounding_box.xmax,
            annotation.bounding_box.ymax,
        ]
        scores[i] = annotation.score
        labels[i] = texts.index(annotation.text)

    masks: NDArray[np.bool_] | None = None
    if response.annotations and response.annotations[0].mask is not None:
        masks = np.array(
            [annotation.mask for annotation in response.annotations], dtype=np.bool_
        )

    return boxes, scores, labels, masks


def nms_bboxes(
    boxes: np.ndarray,
    scores: np.ndarray,
    labels: np.ndarray,
    iou_threshold: float,
    score_threshold: float,
    max_num_detections: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(boxes) == 0:
        return boxes, scores, labels, np.empty((0,), dtype=np.int32)

    num_classes: int = max(labels) + 1
    scores_of_all_classes: NDArray[np.float32] = np.zeros(
        (len(boxes), num_classes), dtype=np.float32
    )
    for i, (score, label) in enumerate(zip(scores, labels)):
        scores_of_all_classes[i, label] = score
    logger.debug(
        "Running NMS: iou_threshold={}, score_threshold={}, max_num_detections={}",
        iou_threshold,
        score_threshold,
        max_num_detections,
    )
    logger.debug(f"Input: num_boxes={len(boxes)}")
    boxes, scores, labels, indices = osam.apis.non_maximum_suppression(
        boxes=boxes,
        scores=scores_of_all_classes,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold,
        max_num_detections=max_num_detections,
    )
    logger.debug(f"Output: num_boxes={len(boxes)}")
    return boxes, scores, labels, indices


def get_shapes_from_bboxes(
    boxes: np.ndarray,
    scores: np.ndarray,
    labels: np.ndarray,
    texts: list[str],
    masks: NDArray[np.bool_] | None,
    shape_type: Literal["rectangle", "polygon", "mask"],
) -> list[Shape]:
    shapes: list[Shape] = []
    for i, (box, score, label) in enumerate(zip(boxes, scores, labels)):
        text: str = texts[label]
        xmin, ymin, xmax, ymax = box

        points: list[list[float]]
        mask: NDArray[np.bool_] | None = None
        if shape_type == "rectangle":
            points = [[xmin, ymin], [xmax, ymax]]
        elif shape_type == "polygon":
            if masks is None:
                points = [
                    [xmin, ymin],
                    [xmax, ymin],
                    [xmax, ymax],
                    [xmin, ymax],
                    [xmin, ymin],
                ]
            else:
                points = compute_polygon_from_mask(mask=masks[i]).tolist()
        elif shape_type == "mask":
            xmin = int(xmin)
            ymin = int(ymin)
            xmax = int(xmax)
            ymax = int(ymax)
            points = [[xmin, ymin], [xmax, ymax]]
            if masks is None:
                mask = np.zeros((ymax - ymin, xmax - xmin), dtype=bool)
            else:
                mask = masks[i][ymin : ymax + 1, xmin : xmax + 1]
        else:
            raise ValueError(f"Unsupported shape_type: {shape_type!r}")

        shape = Shape(
            label=text,
            shape_type=shape_type,
            mask=mask,
            description=json.dumps(dict(score=score.item(), text=text)),
        )
        for point in points:
            shape.addPoint(QtCore.QPointF(point[0], point[1]))
        shapes.append(shape)
    return shapes
