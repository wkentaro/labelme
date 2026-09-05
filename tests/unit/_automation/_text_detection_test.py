from __future__ import annotations

import json
from contextlib import nullcontext

import numpy as np
import osam
import pytest
from numpy.typing import NDArray

from labelme._automation._text_detection import MaskOutputUnavailableError
from labelme._automation._text_detection import get_bboxes_from_texts
from labelme._automation._text_detection import nms_bboxes
from labelme._automation._text_detection import propose_shapes_from_texts
from labelme._shape import Shape


class _FakeOsamSession:
    def __init__(self, *, response: osam.types.GenerateResponse) -> None:
        self.model_name = "stub"
        self._response = response

    def run(self, **_: object) -> osam.types.GenerateResponse:
        return self._response


def _make_annotation(*, with_mask: bool) -> osam.types.Annotation:
    return osam.types.Annotation(
        text="cat",
        score=0.9,
        bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=3, ymax=3),
        mask=np.ones((4, 4), dtype=bool) if with_mask else None,
    )


def _get_bboxes(
    response: osam.types.GenerateResponse,
    /,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[NDArray[np.bool_]] | None]:
    return get_bboxes_from_texts(
        session=_FakeOsamSession(response=response),  # ty: ignore[invalid-argument-type]
        image=np.zeros((4, 4, 3), dtype=np.uint8),
        image_id="img",
        texts=["cat"],
    )


def test_collects_masks_when_every_annotation_has_one() -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            _make_annotation(with_mask=True),
            _make_annotation(with_mask=True),
        ],
    )

    _, _, _, masks = _get_bboxes(response)

    assert masks is not None
    assert len(masks) == 2


def test_masks_is_none_when_no_annotation_has_one() -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            _make_annotation(with_mask=False),
            _make_annotation(with_mask=False),
        ],
    )

    _, _, _, masks = _get_bboxes(response)

    assert masks is None


def test_raises_value_error_when_a_later_mask_is_missing() -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            _make_annotation(with_mask=True),
            _make_annotation(with_mask=False),
        ],
    )

    with pytest.raises(ValueError, match="Mask is missing"):
        _get_bboxes(response)


def test_raises_value_error_when_bounding_box_is_missing() -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            osam.types.Annotation(text="cat", score=0.9, bounding_box=None, mask=None),
        ],
    )

    with pytest.raises(ValueError, match="Bounding box is missing"):
        _get_bboxes(response)


def test_raises_value_error_when_text_is_not_in_the_prompt() -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            osam.types.Annotation(
                text="dog",
                score=0.9,
                bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=3, ymax=3),
                mask=None,
            ),
        ],
    )

    with pytest.raises(ValueError, match="Unexpected text 'dog'"):
        _get_bboxes(response)


def test_nms_bboxes_returns_empty_indices_for_no_boxes() -> None:
    boxes = np.empty((0, 4), dtype=np.float32)
    scores = np.empty((0,), dtype=np.float32)
    labels = np.empty((0,), dtype=np.int32)

    out_boxes, out_scores, out_labels, indices = nms_bboxes(
        boxes=boxes,
        scores=scores,
        labels=labels,
        iou_threshold=0.5,
        score_threshold=0.1,
        max_num_detections=10,
    )

    assert out_boxes is boxes
    assert out_scores is scores
    assert out_labels is labels
    assert indices.shape == (0,)
    assert indices.dtype == np.int32


def test_nms_bboxes_scatters_scores_into_one_hot_class_matrix(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, np.ndarray] = {}

    def fake_non_maximum_suppression(
        *,
        boxes: np.ndarray,
        scores: np.ndarray,
        **_kwargs: object,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        captured["scores"] = scores
        keep = np.array([0], dtype=np.int64)
        return boxes[keep], scores[keep], np.array([0], dtype=np.int64), keep

    monkeypatch.setattr(
        osam.apis, "non_maximum_suppression", fake_non_maximum_suppression
    )

    boxes = np.array([[0, 0, 1, 1], [1, 1, 2, 2]], dtype=np.float32)
    scores = np.array([0.8, 0.6], dtype=np.float32)
    labels = np.array([0, 2], dtype=np.int32)

    out_boxes, _, _, indices = nms_bboxes(
        boxes=boxes,
        scores=scores,
        labels=labels,
        iou_threshold=0.5,
        score_threshold=0.1,
        max_num_detections=10,
    )

    one_hot_scores = captured["scores"]
    assert one_hot_scores.shape == (2, 3)
    np.testing.assert_array_equal(
        one_hot_scores,
        np.array([[0.8, 0.0, 0.0], [0.0, 0.0, 0.6]], dtype=np.float32),
    )
    np.testing.assert_array_equal(indices, np.array([0], dtype=np.int64))
    assert len(out_boxes) == 1


def test_text_proposal_keeps_mask_and_score_alignment_after_suppression() -> None:
    masks = [np.ones((4, 4), dtype=bool) for _ in range(3)]
    masks[1][0, 0] = False
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            osam.types.Annotation(
                text="cat",
                score=score,
                bounding_box=osam.types.BoundingBox(xmin=x, ymin=0, xmax=x + 3, ymax=3),
                mask=mask,
            )
            for x, score, mask in zip([0, 10, 20], [0.2, 0.9, 0.8], masks)
        ],
    )
    existing = Shape(
        label="cat",
        shape_type="mask",
        points=np.array([[20, 0], [23, 3]]),
        mask=masks[2],
        group_id=7,
    )

    shapes = propose_shapes_from_texts(
        session=_FakeOsamSession(response=response),  # ty: ignore[invalid-argument-type]
        image=np.zeros((30, 30, 3), dtype=np.uint8),
        image_id="img",
        texts=["cat"],
        shape_type="mask",
        existing_shapes=[existing],
        iou_threshold=0.5,
        score_threshold=0.5,
        image_size=(30, 30),
        polygon_detail=80,
    )

    (shape,) = shapes
    assert shape.label == "cat"
    assert shape.shape_type == "mask"
    np.testing.assert_array_equal(shape.points, [[10, 0], [13, 3]])
    np.testing.assert_array_equal(shape.mask, masks[1])
    assert shape.description is not None
    assert json.loads(shape.description)["score"] == pytest.approx(0.9)
    assert existing.group_id == 7
    np.testing.assert_array_equal(existing.points, [[20, 0], [23, 3]])


@pytest.mark.parametrize("has_detections", [False, True])
def test_text_proposal_requires_masks_only_for_nonempty_mask_output(
    *, has_detections: bool
) -> None:
    session = _FakeOsamSession(
        response=osam.types.GenerateResponse(
            model="stub",
            annotations=[_make_annotation(with_mask=False)] if has_detections else [],
        )
    )
    expectation = (
        pytest.raises(MaskOutputUnavailableError, match="requires model masks")
        if has_detections
        else nullcontext()
    )
    with expectation:
        assert (
            propose_shapes_from_texts(
                session=session,  # ty: ignore[invalid-argument-type]
                image=np.zeros((4, 4, 3), dtype=np.uint8),
                image_id="img",
                texts=["cat"],
                shape_type="mask",
                existing_shapes=[],
                iou_threshold=0.5,
                score_threshold=0.5,
                image_size=(4, 4),
                polygon_detail=80,
            )
            == []
        )
