from __future__ import annotations

import tracemalloc
from typing import Final
from typing import NamedTuple

import numpy as np
import osam
import pytest
from numpy.typing import NDArray

from labelme._automation import Detection
from labelme._automation import _ai_assist
from labelme._automation import _suppression
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
    assert _detections_from_annotations(annotations=[], at_image_size=[]) == []


def test_detections_from_annotations_sorts_by_score_descending() -> None:
    detections = _detections_from_annotations(
        annotations=[
            _annotation(score=0.2, bbox=(0, 0, 1, 1), mask=None),
            _annotation(score=0.9, bbox=(2, 2, 3, 3), mask=None),
            _annotation(score=0.5, bbox=(4, 4, 5, 5), mask=None),
        ],
        at_image_size=[None] * 3,
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
        at_image_size=[None] * 2,
    )

    assert [detection.bbox for detection in detections] == [
        (2, 2, 3, 3),
        (0, 0, 1, 1),
    ]


def test_detections_from_annotations_flattens_bounding_box() -> None:
    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=(1, 2, 3, 4), mask=None)],
        at_image_size=[None] * 1,
    )

    assert detection.bbox == (1, 2, 3, 4)


def test_detections_from_annotations_keeps_bbox_none_without_bounding_box() -> None:
    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=None, mask=None)],
        at_image_size=[None] * 1,
    )

    assert detection.bbox is None
    assert detection.mask is None


def test_detections_from_annotations_passes_mask_through() -> None:
    mask = np.zeros((2, 2), dtype=bool)
    mask[0, 0] = True

    (detection,) = _detections_from_annotations(
        annotations=[_annotation(score=0.5, bbox=(0, 0, 1, 1), mask=mask)],
        at_image_size=[None] * 1,
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


def _scored_annotation(
    *, score: float, bbox: tuple[int, int, int, int], columns: slice
) -> osam.types.Annotation:
    mask_scores = np.zeros((8, 40), dtype=np.uint8)
    mask_scores[:, columns] = 255
    return osam.types.Annotation(
        score=score,
        bounding_box=osam.types.BoundingBox(
            xmin=bbox[0], ymin=bbox[1], xmax=bbox[2], ymax=bbox[3]
        ),
        mask_scores=mask_scores,
    )


def test_example_box_compares_scored_matches_small_and_enlarges_the_kept_ones() -> None:
    left = (0, 0, 1999, 799)
    right = (2000, 0, 3999, 799)
    existing = Shape(
        shape_type="rectangle",
        points=np.array([[2000, 0], [3999, 799]], dtype=np.float64),
    )

    proposal = AiAssistSession(output_format="mask").propose_shapes(
        annotations=[
            _scored_annotation(score=0.9, bbox=left, columns=slice(0, 20)),
            _scored_annotation(score=0.8, bbox=left, columns=slice(0, 20)),
            _scored_annotation(score=0.7, bbox=right, columns=slice(20, 40)),
        ],
        prompt_kind="example_box",
        points=np.zeros((2, 2)),
        point_labels=np.array([2, 3]),
        existing_shapes=[existing],
        image_size=(4000, 800),
        score_threshold=0.0,
        iou_threshold=0.5,
        sent_size=(400, 80),
        original_size=(4000, 800),
    )

    (shape,) = proposal.new_shapes
    assert shape.mask is not None and shape.mask.shape == (800, 2000)
    assert shape.mask.all()
    assert proposal.matching_existing_shapes == [existing]


def test_point_prompt_compares_full_size_masks_at_the_sent_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def half(*, score: float, xmin: int) -> osam.types.Annotation:
        return osam.types.Annotation(
            score=score,
            bounding_box=osam.types.BoundingBox(
                xmin=xmin, ymin=0, xmax=xmin + 499, ymax=999
            ),
            mask=np.ones((1000, 500), dtype=bool),
        )

    existing = Shape(
        shape_type="polygon",
        points=np.array(
            [(500, 0), (1000, 0), (1000, 1000), (500, 1000)], dtype=np.float64
        ),
    )
    raster_sizes: list[tuple[int, int]] = []
    rasterize = _suppression.rasterize_shape

    def spy(
        *, shape: Shape, xmin: int, ymin: int, width: int, height: int
    ) -> NDArray[np.bool_]:
        raster_sizes.append((height, width))
        return rasterize(shape=shape, xmin=xmin, ymin=ymin, width=width, height=height)

    monkeypatch.setattr(_suppression, "rasterize_shape", spy)

    def propose(existing_shapes: list[Shape]) -> AiAssistProposal:
        return AiAssistSession(output_format="mask").propose_shapes(
            annotations=[half(score=0.9, xmin=0), half(score=0.8, xmin=500)],
            prompt_kind="points",
            points=np.array([[900.5, 500.5]]),
            point_labels=np.array([1]),
            existing_shapes=existing_shapes,
            image_size=(1000, 1000),
            score_threshold=0.0,
            iou_threshold=0.5,
            sent_size=(10, 10),
            original_size=(1000, 1000),
        )

    (shape,) = propose(existing_shapes=[]).new_shapes
    assert shape.mask is not None and shape.mask.shape == (1000, 500)
    assert shape.points.min(axis=0).tolist() == [500, 0]

    covered = propose(existing_shapes=[existing])
    assert covered.new_shapes == []
    assert covered.matching_existing_shapes == [existing]
    assert raster_sizes and max(h * w for h, w in raster_sizes) <= 11 * 11


def test_point_prompt_meets_a_padded_mask_shape_on_the_same_grid() -> None:
    padded = np.zeros((1, 18), dtype=bool)
    padded[0, 14:17] = True
    existing = Shape(
        shape_type="mask",
        points=np.array([[0, 0], [17, 0]], dtype=np.float64),
        mask=padded,
    )

    proposal = AiAssistSession(output_format="mask").propose_shapes(
        annotations=[
            osam.types.Annotation(
                score=0.9,
                bounding_box=osam.types.BoundingBox(xmin=14, ymin=0, xmax=16, ymax=0),
                mask=np.ones((1, 3), dtype=bool),
            )
        ],
        prompt_kind="points",
        points=np.array([[15.5, 0.5]]),
        point_labels=np.array([1]),
        existing_shapes=[existing],
        image_size=(20, 1),
        score_threshold=0.0,
        iou_threshold=0.5,
        sent_size=(2, 1),
        original_size=(20, 1),
    )

    assert proposal.new_shapes == []
    assert proposal.matching_existing_shapes == [existing]


def _polygon_proposal_peak_bytes(*, count: int, object_size: int) -> int:
    annotations = [
        _scored_annotation(
            score=1 - i / 10,
            bbox=(i * object_size, 0, (i + 1) * object_size - 1, object_size - 1),
            columns=slice(i * 4, i * 4 + 4),
        )
        for i in range(count)
    ]
    tracemalloc.start()
    proposal = AiAssistSession(output_format="polygon").propose_shapes(
        annotations=annotations,
        prompt_kind="example_box",
        points=np.zeros((2, 2)),
        point_labels=np.array([2, 3]),
        existing_shapes=[],
        image_size=(10 * object_size, object_size),
        score_threshold=0.0,
        iou_threshold=0.5,
        sent_size=(400, 40),
        original_size=(10 * object_size, object_size),
    )
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(proposal.new_shapes) == count
    return peak_bytes


def test_example_box_holds_one_enlarged_mask_at_a_time() -> None:
    object_size = 4000
    _polygon_proposal_peak_bytes(count=1, object_size=object_size)

    one = _polygon_proposal_peak_bytes(count=1, object_size=object_size)
    ten = _polygon_proposal_peak_bytes(count=10, object_size=object_size)

    assert ten < one + object_size**2 // 2
