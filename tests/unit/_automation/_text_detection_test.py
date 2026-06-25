from __future__ import annotations

import numpy as np
import osam
import pytest
from numpy.typing import NDArray

from labelme._automation._text_detection import get_bboxes_from_texts


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
