from __future__ import annotations

import dataclasses

import numpy as np
import osam
from loguru import logger
from numpy.typing import NDArray

from .._ai_models import supports_point_prompts
from .._shape import Shape
from ._osam_session import OsamSession
from ._shape_builders import Detection
from ._shape_builders import shapes_from_detections
from ._suppression import match_detections_to_existing_shapes
from ._suppression import suppress_detections_greedy
from ._types import AiOutputFormat
from ._types import AiPromptKind


@dataclasses.dataclass(frozen=True)
class AiAssistProposal:
    new_shapes: list[Shape]
    matching_existing_shapes: list[Shape]
    candidate_detection_count: int
    existing_shape_match_detection_count: int

    @property
    def is_every_candidate_detection_matched_to_existing_shape(self) -> bool:
        return (
            self.candidate_detection_count > 0
            and self.existing_shape_match_detection_count
            == self.candidate_detection_count
        )


class AiAssistSession:
    model_name: str
    output_format: AiOutputFormat
    _session: OsamSession | None

    def __init__(
        self,
        model_name: str = "sam2:latest",
        output_format: AiOutputFormat = "polygon",
    ) -> None:
        self.model_name = model_name
        self.output_format = output_format
        self._session = None

    def _get_session(self) -> OsamSession:
        if self._session is None or self._session.model_name != self.model_name:
            self._session = OsamSession(model_name=self.model_name)
        return self._session

    def propose_shapes(
        self,
        *,
        image: NDArray[np.uint8],
        image_id: str,
        prompt_kind: AiPromptKind,
        points: NDArray[np.floating],
        point_labels: NDArray[np.intp],
        existing_shapes: list[Shape],
    ) -> AiAssistProposal:
        if prompt_kind == "points" and not supports_point_prompts(
            model_name=self.model_name
        ):
            raise ValueError(f"{self.model_name} does not support point prompts")
        response: osam.types.GenerateResponse = self._get_session().run(
            image=image,
            image_id=image_id,
            points=points,
            point_labels=point_labels,
        )
        # iou_threshold is hardcoded because the AI Assist flow has no
        # user-facing IoU control (unlike the AI Text Prompt flow); 0.5 matches
        # the AI Text Prompt widget default.
        detections = _detections_from_annotations(response.annotations)
        if prompt_kind == "points" and detections:
            detections = [
                max(
                    detections,
                    key=lambda detection: (
                        _count_satisfied_prompt_points(
                            detection=detection,
                            points=points,
                            point_labels=point_labels,
                        ),
                        detection.score,
                    ),
                )
            ]
        detections = suppress_detections_greedy(
            detections=detections,
            iou_threshold=0.5,
        )
        matches = match_detections_to_existing_shapes(
            detections=detections,
            existing_shapes=existing_shapes,
        )
        existing_shape_match_detection_count = len(detections) - len(
            matches.new_detections
        )
        return AiAssistProposal(
            new_shapes=shapes_from_detections(
                detections=matches.new_detections,
                shape_type=self.output_format,
            ),
            matching_existing_shapes=matches.matching_shapes,
            candidate_detection_count=len(detections),
            existing_shape_match_detection_count=existing_shape_match_detection_count,
        )


def _count_satisfied_prompt_points(
    *,
    detection: Detection,
    points: NDArray[np.floating],
    point_labels: NDArray[np.intp],
) -> int:
    return sum(
        _is_point_inside_detection(detection=detection, point=point)
        == (point_label == 1)
        for point, point_label in zip(points, point_labels, strict=True)
    )


def _is_point_inside_detection(
    *,
    detection: Detection,
    point: NDArray[np.floating],
) -> bool:
    if detection.bbox is None:
        return False
    xmin, ymin, xmax, ymax = (int(round(coordinate)) for coordinate in detection.bbox)
    x, y = (int(round(coordinate)) for coordinate in point)
    if not (xmin <= x <= xmax and ymin <= y <= ymax):
        return False
    if detection.mask is None:
        return True
    return bool(detection.mask[y - ymin, x - xmin])


def _detections_from_annotations(
    annotations: list[osam.types.Annotation],
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
                score=annotation.score if annotation.score is not None else 0.0,
            )
        )
    return detections
