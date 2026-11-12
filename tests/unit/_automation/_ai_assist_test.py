from __future__ import annotations

from typing import Final

import numpy as np
import osam
import pytest
from numpy.typing import NDArray

from labelme._automation import Detection
from labelme._automation import _ai_assist
from labelme._automation._ai_assist import AiAssistProposal
from labelme._automation._ai_assist import AiAssistSession
from labelme._automation._ai_assist import _detections_from_annotations
from labelme._automation._ai_assist import _is_point_inside_detection
from labelme._shape import Shape


def _propose(
    *,
    session: AiAssistSession,
    prompt_kind: _ai_assist.AiPromptKind,
    existing_shapes: list[Shape] | None,
    annotations: list[osam.types.Annotation],
) -> AiAssistProposal:
    if prompt_kind in ("box", "example_box"):
        points = np.zeros((2, 2))
        point_labels = np.array([2, 3])
    else:
        points = np.zeros((1, 2))
        point_labels = np.array([1])
    return session.propose_shapes(
        annotations=annotations,
        prompt_kind=prompt_kind,
        points=points,
        point_labels=point_labels,
        existing_shapes=[] if existing_shapes is None else existing_shapes,
        score_threshold=0.0,
        iou_threshold=0.5,
    )


def test_point_prompt_uses_best_answer() -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            osam.types.Annotation(
                score=0.3,
                bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=5, ymax=5),
            ),
            osam.types.Annotation(
                score=0.9,
                bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10),
            ),
        ],
    )
    session = AiAssistSession(model_name="a", output_format="rectangle")

    proposal = _propose(
        session=session,
        annotations=response.annotations,
        prompt_kind="points",
        existing_shapes=None,
    )

    assert len(proposal.new_shapes) == 1
    assert proposal.new_shapes[0].shape_type == "rectangle"
    np.testing.assert_array_equal(
        proposal.new_shapes[0].points,
        [[0, 0], [10, 10]],
    )

    _propose(
        session=session,
        annotations=response.annotations,
        prompt_kind="points",
        existing_shapes=None,
    )

    session.model_name = "b"
    _propose(
        session=session,
        annotations=response.annotations,
        prompt_kind="points",
        existing_shapes=None,
    )


def test_default_model_name_and_output_format() -> None:
    session = AiAssistSession()
    assert session.model_name == "sam2:latest"
    assert session.output_format == "polygon"
    assert session.polygon_detail == 60

    session.model_name = "efficientsam:latest"
    session.output_format = "mask"
    assert session.model_name == "efficientsam:latest"
    assert session.output_format == "mask"


def test_polygon_detail_controls_ai_polygon_points() -> None:
    mask = np.zeros((100, 100), dtype=bool)
    mask[20:80, 30:70] = True
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[_annotation(score=0.9, bbox=(0, 0, 99, 99), mask=mask)],
    )
    session = AiAssistSession(polygon_detail=100)

    maximum_detail = _propose(
        session=session,
        annotations=response.annotations,
        prompt_kind="points",
        existing_shapes=None,
    ).new_shapes
    session.polygon_detail = 80
    balanced_detail = _propose(
        session=session,
        annotations=response.annotations,
        prompt_kind="points",
        existing_shapes=None,
    ).new_shapes

    assert len(maximum_detail[0].points) == 8
    assert len(balanced_detail[0].points) == 4


def test_polygon_proposal_groups_disconnected_lands() -> None:
    mask = np.zeros((100, 100), dtype=bool)
    mask[10:40, 10:40] = True
    mask[60:90, 60:90] = True
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[_annotation(score=0.9, bbox=(0, 0, 99, 99), mask=mask)],
    )

    shapes = _propose(
        session=AiAssistSession(),
        annotations=response.annotations,
        prompt_kind="points",
        existing_shapes=None,
    ).new_shapes

    assert len(shapes) == 2
    assert shapes[0].group_id == shapes[1].group_id


def _annotation(
    *,
    score: float | None,
    bbox: tuple[int, int, int, int] | None,
    mask: NDArray[np.bool_] | None,
) -> osam.types.Annotation:
    bounding_box = (
        osam.types.BoundingBox(xmin=bbox[0], ymin=bbox[1], xmax=bbox[2], ymax=bbox[3])
        if bbox is not None
        else None
    )
    return osam.types.Annotation(score=score, bounding_box=bounding_box, mask=mask)


@pytest.fixture
def existing_rectangle() -> Shape:
    return Shape(
        shape_type="rectangle",
        points=np.array([[0, 0], [10, 10]], dtype=np.float64),
    )


def test_detections_from_annotations_empty_returns_empty() -> None:
    assert _detections_from_annotations(annotations=[]) == []


def test_detections_from_annotations_sorts_by_score_descending() -> None:
    detections = _detections_from_annotations(
        annotations=[
            _annotation(score=0.2, bbox=(0, 0, 1, 1), mask=None),
            _annotation(score=0.9, bbox=(2, 2, 3, 3), mask=None),
            _annotation(score=0.5, bbox=(4, 4, 5, 5), mask=None),
        ]
    )

    assert [detection.bbox for detection in detections] == [
        (2, 2, 3, 3),
        (4, 4, 5, 5),
        (0, 0, 1, 1),
    ]


def test_detections_from_annotations_treats_missing_score_as_zero() -> None:
    detections = _detections_from_annotations(
        annotations=[
            _annotation(score=None, bbox=(0, 0, 1, 1), mask=None),
            _annotation(score=0.5, bbox=(2, 2, 3, 3), mask=None),
        ]
    )

    assert [detection.bbox for detection in detections] == [
        (2, 2, 3, 3),
        (0, 0, 1, 1),
    ]


def test_detections_from_annotations_flattens_bounding_box() -> None:
    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=(1, 2, 3, 4), mask=None)]
    )

    assert detection.bbox == (1, 2, 3, 4)


def test_detections_from_annotations_keeps_bbox_none_without_bounding_box() -> None:
    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=None, mask=None)]
    )

    assert detection.bbox is None
    assert detection.mask is None


def test_detections_from_annotations_passes_mask_through() -> None:
    mask = np.zeros((2, 2), dtype=bool)
    mask[0, 0] = True

    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=(0, 0, 1, 1), mask=mask)]
    )

    np.testing.assert_array_equal(detection.mask, mask)


def test_point_inside_detection_uses_rounded_mask_origin() -> None:
    mask = np.zeros((30, 22), dtype=bool)
    mask[0, 0] = True
    detection = Detection(bbox=(10.4, 20.6, 30.9, 50.1), mask=mask)

    is_inside = _is_point_inside_detection(
        detection=detection,
        point=np.array([10.0, 21.0]),
    )

    assert is_inside is True


def test_point_inside_detection_reads_the_pixel_under_the_point() -> None:
    # The canvas spans pixel c from c to c + 1, so 10.7 is still pixel 10.
    mask = np.zeros((2, 2), dtype=bool)
    mask[0, 0] = True
    detection = Detection(bbox=(10, 20, 11, 21), mask=mask)

    assert _is_point_inside_detection(detection=detection, point=np.array([10.7, 20.7]))
    assert not _is_point_inside_detection(
        detection=detection, point=np.array([11.0, 20.0])
    )


def test_point_prompt_reports_best_matching_existing_shape() -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            _annotation(score=0.9, bbox=(20, 20, 30, 30), mask=None),
            _annotation(score=0.8, bbox=(0, 0, 10, 10), mask=None),
        ],
    )
    containing = Shape(
        shape_type="rectangle",
        points=np.array([[-5, -5], [15, 15]], dtype=np.float64),
    )
    exact = Shape(
        shape_type="rectangle",
        points=np.array([[0, 0], [10, 10]], dtype=np.float64),
    )
    session = AiAssistSession(output_format="rectangle")

    proposal = session.propose_shapes(
        annotations=response.annotations,
        prompt_kind="points",
        points=np.array([[5, 5], [25, 25]], dtype=np.float64),
        point_labels=np.array([1, 0]),
        existing_shapes=[containing, exact],
        score_threshold=0.0,
        iou_threshold=0.5,
    )

    assert proposal.new_shapes == []
    assert len(proposal.matching_existing_shapes) == 1
    assert proposal.matching_existing_shapes[0] is exact


@pytest.mark.parametrize(
    ("existing_bbox", "proposal_bbox"),
    [
        ((0, 0, 10, 10), (3, 3, 5, 5)),
        ((3, 3, 5, 5), (0, 0, 10, 10)),
        ((0, 0, 10, 10), (2, 0, 12, 10)),
    ],
)
def test_point_prompt_reports_matching_existing_shape(
    *,
    existing_bbox: tuple[int, int, int, int],
    proposal_bbox: tuple[int, int, int, int],
) -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[_annotation(score=0.9, bbox=proposal_bbox, mask=None)],
    )
    existing = Shape(
        shape_type="rectangle",
        points=np.array([existing_bbox[:2], existing_bbox[2:]], dtype=np.float64),
    )
    session = AiAssistSession(output_format="rectangle")

    proposal = _propose(
        session=session,
        annotations=response.annotations,
        existing_shapes=[existing],
        prompt_kind="points",
    )

    assert proposal.new_shapes == []
    assert len(proposal.matching_existing_shapes) == 1
    assert proposal.matching_existing_shapes[0] is existing


def test_example_box_suppresses_only_proposals_matching_existing_shapes(
    *,
    existing_rectangle: Shape,
) -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            _annotation(score=0.9, bbox=(0, 0, 10, 10), mask=None),
            _annotation(score=0.8, bbox=(20, 20, 30, 30), mask=None),
        ],
    )
    session = AiAssistSession(model_name="sam3:latest", output_format="rectangle")

    proposal = _propose(
        session=session,
        annotations=response.annotations,
        prompt_kind="example_box",
        existing_shapes=[existing_rectangle],
    )

    assert len(proposal.new_shapes) == 1
    np.testing.assert_array_equal(
        proposal.new_shapes[0].points,
        [[20, 20], [30, 30]],
    )
    assert len(proposal.matching_existing_shapes) == 1
    assert proposal.matching_existing_shapes[0] is existing_rectangle


def test_single_result_example_box_reports_matching_existing_shape(
    *,
    existing_rectangle: Shape,
) -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[_annotation(score=0.9, bbox=(0, 0, 10, 10), mask=None)],
    )
    session = AiAssistSession(model_name="sam3:latest", output_format="rectangle")

    proposal = _propose(
        session=session,
        annotations=response.annotations,
        prompt_kind="example_box",
        existing_shapes=[existing_rectangle],
    )

    assert proposal.new_shapes == []
    assert len(proposal.matching_existing_shapes) == 1
    assert proposal.matching_existing_shapes[0] is existing_rectangle


_DUPLICATE_ANNOTATIONS: Final = [
    _annotation(score=0.9, bbox=(0, 0, 10, 10), mask=None),
    _annotation(score=0.8, bbox=(0, 0, 10, 10), mask=None),
]


def test_example_box_matches_existing_shape_after_greedy_suppression(
    *,
    existing_rectangle: Shape,
) -> None:
    proposal = _propose(
        session=AiAssistSession(output_format="rectangle"),
        annotations=_DUPLICATE_ANNOTATIONS,
        prompt_kind="example_box",
        existing_shapes=[existing_rectangle],
    )

    assert proposal.new_shapes == []
    assert len(proposal.matching_existing_shapes) == 1
    assert proposal.matching_existing_shapes[0] is existing_rectangle


def test_example_box_still_applies_greedy_suppression_among_new_detections() -> None:
    proposal = _propose(
        session=AiAssistSession(output_format="rectangle"),
        annotations=_DUPLICATE_ANNOTATIONS,
        prompt_kind="example_box",
        existing_shapes=None,
    )

    assert len(proposal.new_shapes) == 1
    np.testing.assert_array_equal(
        proposal.new_shapes[0].points,
        [[0, 0], [10, 10]],
    )
    assert proposal.matching_existing_shapes == []


def test_box_keeps_the_candidate_that_fills_the_box() -> None:
    session = AiAssistSession(model_name="sam3:latest", output_format="rectangle")

    proposal = session.propose_shapes(
        annotations=[
            _annotation(score=0.8, bbox=(10, 10, 30, 30), mask=None),
            _annotation(score=0.9, bbox=(60, 60, 80, 80), mask=None),
        ],
        prompt_kind="box",
        points=np.array([[10.0, 10.0], [30.0, 30.0]]),
        point_labels=np.array([2, 3]),
        existing_shapes=[],
        score_threshold=0.0,
        iou_threshold=0.5,
    )

    assert len(proposal.new_shapes) == 1
    np.testing.assert_array_equal(proposal.new_shapes[0].points, [[10, 10], [30, 30]])


def test_example_box_covered_candidate_does_not_hide_a_new_one(
    *,
    existing_rectangle: Shape,
) -> None:
    # The candidate on the existing Shape overlaps the one beside it; once
    # covered it must not suppress that one.
    proposal = _propose(
        session=AiAssistSession(output_format="rectangle"),
        annotations=[
            _annotation(score=0.9, bbox=(2, 0, 12, 10), mask=None),
            _annotation(score=0.8, bbox=(5, 0, 15, 10), mask=None),
        ],
        prompt_kind="example_box",
        existing_shapes=[existing_rectangle],
    )

    (shape,) = proposal.new_shapes
    np.testing.assert_array_equal(shape.points, [[5, 0], [15, 10]])
