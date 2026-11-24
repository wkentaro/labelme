from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from numpy.typing import NDArray

from .._shape import Shape
from ._geometry import round_bbox_to_int
from ._mask_logits import MaskLogits
from ._scaling import UNSCALED
from ._scaling import Scale
from ._scaling import scale_pixel_box
from ._shape_builders import Detection
from ._shape_builders import shapes_from_detections
from ._suppression import match_detections_to_existing_shapes
from ._suppression import suppress_detections_greedy
from ._types import AiOutputFormat
from ._types import AiPromptKind

if TYPE_CHECKING:
    import osam


@dataclasses.dataclass(frozen=True)
class AiAssistProposal:
    new_shapes: list[Shape]
    matching_existing_shapes: list[Shape]


class AiAssistSession:
    model_name: str
    output_format: AiOutputFormat
    polygon_detail: int

    def __init__(
        self,
        *,
        model_name: str = "sam2:latest",
        output_format: AiOutputFormat = "polygon",
        polygon_detail: int = 60,
    ) -> None:
        self.model_name = model_name
        self.output_format = output_format
        self.polygon_detail = polygon_detail

    def propose_shapes(
        self,
        *,
        annotations: list[osam.types.Annotation],
        prompt_kind: AiPromptKind,
        points: NDArray[np.floating],
        point_labels: NDArray[np.intp],
        existing_shapes: list[Shape],
        image_size: tuple[int, int] | None = None,
        score_threshold: float,
        iou_threshold: float,
        scale_to_image: Scale = UNSCALED,
        sent_size: tuple[int, int],
        shown_as_mask: bool = False,
    ) -> AiAssistProposal:
        saved_as_mask = self.output_format == "mask"
        detections = [
            detection
            for detection in _detections_from_annotations(
                annotations=annotations,
                sent_size=sent_size,
            )
            if detection.score >= score_threshold
        ]
        if prompt_kind == "box" and detections:
            # One Shape per box, whichever model answered: the candidate that
            # best fills the box, then the most confident.
            box = (points / np.asarray(scale_to_image, dtype=np.float64)).ravel()
            detections = [
                max(
                    detections,
                    key=lambda detection: (
                        _box_iou(bbox=detection.bbox, box=box),
                        detection.score,
                    ),
                )
            ]
        elif prompt_kind == "points" and detections:
            detections = [
                max(
                    detections,
                    key=lambda detection: (
                        _count_satisfied_prompt_points(
                            detection=detection,
                            points=points,
                            point_labels=point_labels,
                            scale_to_image=scale_to_image,
                            saved_as_mask=saved_as_mask,
                        ),
                        detection.score,
                    ),
                )
            ]
        # Existing Shapes cover candidates before candidates suppress each
        # other, so a covered candidate never hides a new one.
        matches = match_detections_to_existing_shapes(
            detections=detections,
            existing_shapes=existing_shapes,
            scale_to_image=scale_to_image,
            saved_as_mask=saved_as_mask,
        )
        new_detections = suppress_detections_greedy(
            detections=matches.new_detections,
            iou_threshold=iou_threshold,
            scale_to_image=scale_to_image,
            saved_as_mask=saved_as_mask,
        )
        return AiAssistProposal(
            new_shapes=shapes_from_detections(
                detections=new_detections,
                shape_type="mask" if shown_as_mask else self.output_format,
                image_size=image_size,
                polygon_detail=self.polygon_detail,
                scale_to_image=scale_to_image,
            ),
            matching_existing_shapes=matches.matching_shapes,
        )


def _box_iou(
    *, bbox: tuple[float, float, float, float] | None, box: NDArray[np.floating]
) -> float:
    if bbox is None:
        return 0.0
    ax1, ay1, ax2, ay2 = bbox
    bx1, by1, bx2, by2 = (float(v) for v in box)
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def _count_satisfied_prompt_points(
    *,
    detection: Detection,
    points: NDArray[np.floating],
    point_labels: NDArray[np.intp],
    scale_to_image: Scale,
    saved_as_mask: bool,
) -> int:
    # Box corners (labels 2, 3) say nothing about which mask is right.
    return sum(
        _is_point_inside_detection(
            detection=detection,
            point=point,
            scale_to_image=scale_to_image,
            saved_as_mask=saved_as_mask,
        )
        == (point_label == 1)
        for point, point_label in zip(points, point_labels, strict=True)
        if point_label in (0, 1)
    )


def _is_point_inside_detection(
    *,
    detection: Detection,
    point: NDArray[np.floating],
    scale_to_image: Scale,
    saved_as_mask: bool,
) -> bool:
    if detection.bbox is None:
        return False
    logits = detection.mask_logits if saved_as_mask else None
    # The canvas spans pixel c from c to c + 1.
    if saved_as_mask:
        x, y = (int(np.floor(coordinate)) for coordinate in point)
        if logits is not None and logits.holds(pixel=(x, y), scale=scale_to_image):
            return True
        x0, y0, x1, y1 = scale_pixel_box(
            box=(x, y, x, y), factor=(1 / scale_to_image[0], 1 / scale_to_image[1])
        )
    else:
        x0, y0 = x1, y1 = [
            int(np.floor(coordinate / float(factor)))
            for coordinate, factor in zip(point, scale_to_image)
        ]
    xmin, ymin, xmax, ymax = round_bbox_to_int(bbox=detection.bbox)
    if detection.mask is None:
        inside = x0 <= xmax and xmin <= x1 and y0 <= ymax and ymin <= y1
    else:
        inside = bool(
            detection.mask[
                max(y0 - ymin, 0) : max(y1 - ymin + 1, 0),
                max(x0 - xmin, 0) : max(x1 - xmin + 1, 0),
            ].any()
        )
    # A Mask Shape whose redraw comes out empty is the sent mask scaled up.
    return inside and (logits is None or logits.draws_nothing(scale=scale_to_image))


def _detections_from_annotations(
    *,
    annotations: list[osam.types.Annotation],
    sent_size: tuple[int, int],
) -> list[Detection]:
    if not annotations:
        logger.warning("No annotations returned")
        return []
    sorted_annotations = sorted(
        annotations,
        key=lambda a: a.score if a.score is not None else 0,
        reverse=True,
    )
    detections: list[Detection] = []
    for annotation in sorted_annotations:
        bbox: tuple[float, float, float, float] | None = None
        if annotation.bounding_box is not None:
            bb = annotation.bounding_box
            bbox = (bb.xmin, bb.ymin, bb.xmax, bb.ymax)
        detections.append(
            Detection(
                bbox=bbox,
                mask=annotation.mask,
                mask_logits=MaskLogits.from_annotation(
                    annotation=annotation, sent_size=sent_size
                ),
                score=annotation.score if annotation.score is not None else 0.0,
            )
        )
    return detections
