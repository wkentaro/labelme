from __future__ import annotations

from fractions import Fraction
from typing import Final
from typing import NamedTuple

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


class _Response(NamedTuple):
    annotations: list[osam.types.Annotation]


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
        sent_size=(100, 100),
        annotations=annotations,
        prompt_kind=prompt_kind,
        points=points,
        point_labels=point_labels,
        existing_shapes=[] if existing_shapes is None else existing_shapes,
        score_threshold=0.0,
        iou_threshold=0.5,
    )


def test_point_prompt_uses_best_answer() -> None:
    response = _Response(
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
    response = _Response(
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
    response = _Response(
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
    assert _detections_from_annotations(annotations=[], sent_size=(100, 100)) == []


def test_detections_from_annotations_sorts_by_score_descending() -> None:
    detections = _detections_from_annotations(
        annotations=[
            _annotation(score=0.2, bbox=(0, 0, 1, 1), mask=None),
            _annotation(score=0.9, bbox=(2, 2, 3, 3), mask=None),
            _annotation(score=0.5, bbox=(4, 4, 5, 5), mask=None),
        ],
        sent_size=(100, 100),
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
        ],
        sent_size=(100, 100),
    )

    assert [detection.bbox for detection in detections] == [
        (2, 2, 3, 3),
        (0, 0, 1, 1),
    ]


def test_detections_from_annotations_flattens_bounding_box() -> None:
    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=(1, 2, 3, 4), mask=None)],
        sent_size=(100, 100),
    )

    assert detection.bbox == (1, 2, 3, 4)


def test_detections_from_annotations_keeps_bbox_none_without_bounding_box() -> None:
    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=None, mask=None)],
        sent_size=(100, 100),
    )

    assert detection.bbox is None
    assert detection.mask is None


def test_detections_from_annotations_passes_mask_through() -> None:
    mask = np.zeros((2, 2), dtype=bool)
    mask[0, 0] = True

    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=(0, 0, 1, 1), mask=mask)],
        sent_size=(100, 100),
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
    response = _Response(
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
        sent_size=(100, 100),
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
    response = _Response(
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
    response = _Response(
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
    response = _Response(
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
        sent_size=(100, 100),
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


@pytest.mark.parametrize(
    ("output_format", "expected_bounds"),
    [
        ("mask", [[8, 8], [23, 23]]),
        ("rectangle", [[8, 8], [23, 23]]),
        pytest.param("polygon", [[8, 8], [24, 24]], id="polygon-pixel-edges"),
    ],
)
def test_shapes_from_a_shrunk_image_scale_to_the_image(
    *, output_format: _ai_assist.AiOutputFormat, expected_bounds: list[list[int]]
) -> None:
    proposal = AiAssistSession(
        output_format=output_format, polygon_detail=0
    ).propose_shapes(
        sent_size=(10, 10),
        annotations=[
            _annotation(score=0.9, bbox=(2, 2, 5, 5), mask=np.ones((4, 4), bool))
        ],
        prompt_kind="points",
        points=np.array([[12.0, 12.0]]),
        point_labels=np.array([1]),
        existing_shapes=[],
        image_size=(40, 40),
        score_threshold=0.0,
        iou_threshold=0.5,
        scale_to_image=(Fraction(4), Fraction(4)),
    )

    (shape,) = proposal.new_shapes
    np.testing.assert_allclose(
        [shape.points.min(axis=0), shape.points.max(axis=0)],
        expected_bounds,
        atol=0.01,
    )
    if output_format == "mask":
        assert shape.mask is not None
        assert shape.mask.shape == (16, 16)


def test_a_shrunk_image_matches_the_existing_shape_it_covers() -> None:
    existing = Shape(
        shape_type="rectangle",
        points=np.array([[8, 8], [23, 23]], dtype=np.float64),
    )

    proposal = AiAssistSession(output_format="rectangle").propose_shapes(
        sent_size=(25, 25),
        annotations=[_annotation(score=0.9, bbox=(2, 2, 5, 5), mask=None)],
        prompt_kind="points",
        points=np.array([[12.0, 12.0]]),
        point_labels=np.array([1]),
        existing_shapes=[existing],
        score_threshold=0.0,
        iou_threshold=0.5,
        scale_to_image=(Fraction(4), Fraction(4)),
    )

    assert proposal.new_shapes == []
    assert proposal.matching_existing_shapes == [existing]


@pytest.mark.parametrize(
    ("output_format", "new_count"),
    [
        pytest.param("mask", 0, id="a-mask-merges-its-three-sent-rows"),
        pytest.param("rectangle", 1, id="a-rectangle-keeps-its-row"),
    ],
)
def test_a_proposal_shown_as_masks_adds_what_the_output_format_adds(
    *, output_format: _ai_assist.AiOutputFormat, new_count: int
) -> None:
    two_thirds_of_the_saved_mask = Shape(
        shape_type="mask",
        points=np.array([[20.0, 1.0], [119.0, 1.0]]),
        mask=np.ones((1, 100), dtype=bool),
    )
    session = AiAssistSession(output_format=output_format)

    def propose(*, shown_as_mask: bool) -> AiAssistProposal:
        return session.propose_shapes(
            annotations=[
                _annotation(
                    score=0.9, bbox=(0, 3, 49, 3), mask=np.ones((1, 50), dtype=bool)
                )
            ],
            prompt_kind="points",
            points=np.array([[10.0, 1.5]]),
            point_labels=np.array([1]),
            existing_shapes=[two_thirds_of_the_saved_mask],
            score_threshold=0.0,
            iou_threshold=0.5,
            scale_to_image=(Fraction(2), Fraction(1, 3)),
            sent_size=(60, 9),
            shown_as_mask=shown_as_mask,
        )

    assert [shape.shape_type for shape in propose(shown_as_mask=False).new_shapes] == (
        [output_format] * new_count
    )
    assert [shape.shape_type for shape in propose(shown_as_mask=True).new_shapes] == (
        ["mask"] * new_count
    )


@pytest.mark.parametrize(
    ("existing_column", "new_count"),
    [
        pytest.param(5, 0, id="over-the-sent-mask"),
        pytest.param(6, 1, id="over-the-mask-drawn-from-logits"),
    ],
)
def test_a_guess_drawn_from_logits_adds_what_the_rectangle_click_adds(
    *, existing_column: int, new_count: int
) -> None:
    one_logit = 256
    annotation = osam.types.Annotation(
        score=0.9,
        bounding_box=osam.types.BoundingBox(xmin=5, ymin=0, xmax=5, ymax=62),
        mask=np.ones((63, 1), dtype=bool),
        mask_logits=np.array(
            [[32768 - 100 * one_logit, 32768 + one_logit, 32768, 0]], dtype=np.uint16
        ),
        mask_logits_box=(4.0, 0.0, 8.0, 63.0),
    )
    existing = Shape(
        shape_type="mask",
        points=np.array([[existing_column, 0], [existing_column, 64]]),
        mask=np.ones((65, 1), dtype=bool),
    )
    session = AiAssistSession(output_format="rectangle")

    def propose(*, shown_as_mask: bool) -> AiAssistProposal:
        return session.propose_shapes(
            annotations=[annotation],
            prompt_kind="points",
            points=np.array([[5.5, 30.0]]),
            point_labels=np.array([1]),
            existing_shapes=[existing],
            score_threshold=0.0,
            iou_threshold=0.5,
            scale_to_image=(Fraction(65, 63), Fraction(65, 63)),
            sent_size=(63, 63),
            shown_as_mask=shown_as_mask,
        )

    click, guess = propose(shown_as_mask=False), propose(shown_as_mask=True)

    assert [shape.shape_type for shape in click.new_shapes] == (
        ["rectangle"] * new_count
    )
    assert [shape.points.tolist() for shape in guess.new_shapes] == (
        [[[6, 0], [6, 64]]] * new_count
    )


@pytest.mark.parametrize(
    ("output_format", "left_edge"),
    [
        pytest.param("mask", 0, id="the-mask-drawn-over-the-click"),
        pytest.param("rectangle", 8, id="the-more-confident-sent-mask"),
    ],
)
def test_a_click_picks_the_candidate_whose_saved_shape_covers_it(
    *, output_format: _ai_assist.AiOutputFormat, left_edge: int
) -> None:
    one_logit = 256
    drawn_right_of_the_click = osam.types.Annotation(
        score=0.9,
        bounding_box=osam.types.BoundingBox(xmin=2, ymin=0, xmax=7, ymax=7),
        mask=np.ones((8, 6), dtype=bool),
        mask_logits=np.array(
            [[32768 - 3 * one_logit, 32768 + 37 * one_logit]], dtype=np.uint16
        ),
        mask_logits_box=(0.0, 0.0, 8.0, 8.0),
    )
    drawn_over_the_click = osam.types.Annotation(
        score=0.8,
        bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=7, ymax=7),
        mask=np.ones((8, 8), dtype=bool),
        mask_logits=np.full((1, 2), 32768 + one_logit, dtype=np.uint16),
        mask_logits_box=(0.0, 0.0, 8.0, 8.0),
    )

    proposal = AiAssistSession(output_format=output_format).propose_shapes(
        annotations=[drawn_right_of_the_click, drawn_over_the_click],
        prompt_kind="points",
        points=np.array([[8.5, 16.0]]),
        point_labels=np.array([1]),
        existing_shapes=[],
        score_threshold=0.0,
        iou_threshold=0.5,
        scale_to_image=(Fraction(4), Fraction(4)),
        sent_size=(8, 8),
    )

    [shape] = proposal.new_shapes
    assert shape.points.min(axis=0)[0] == left_edge
