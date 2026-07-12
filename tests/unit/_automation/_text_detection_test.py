from __future__ import annotations

import numpy as np
import osam
import pytest
from numpy.typing import NDArray

from labelme._automation._text_detection import get_bboxes_from_texts
from labelme._automation._text_detection import nms_bboxes


class _FakeOsamSession:
    def __init__(self, response: osam.types.GenerateResponse) -> None:
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
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[NDArray[np.bool_]] | None]:
    return get_bboxes_from_texts(
        session=_FakeOsamSession(response),  # ty: ignore[invalid-argument-type]
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, np.ndarray] = {}

    def fake_non_maximum_suppression(
        *,
        boxes: np.ndarray,
        scores: np.ndarray,
        iou_threshold: float,
        score_threshold: float,
        max_num_detections: int,
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
