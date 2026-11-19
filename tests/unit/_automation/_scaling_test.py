from __future__ import annotations

import numpy as np
import pytest

from labelme._automation._scaling import scale_pixel_box
from labelme._automation._scaling import scale_shape
from labelme._shape import Shape


@pytest.mark.parametrize(
    ("box", "factor", "expected"),
    [
        ((0, 0, 0, 0), (4.0, 2.0), (0, 0, 3, 1)),
        ((8, 4, 23, 11), (0.25, 0.5), (2, 2, 5, 5)),
        ((5, 5, 5, 5), (0.1, 0.1), (0, 0, 0, 0)),
        ((-1, -1, -1, -1), (0.25, 0.25), (-1, -1, -1, -1)),
        ((0, 1023, 1023, 1023), (1.0, 0.5), (0, 511, 1023, 511)),
    ],
)
def test_scale_pixel_box_maps_whole_pixels(
    *,
    box: tuple[int, int, int, int],
    factor: tuple[float, float],
    expected: tuple[int, int, int, int],
) -> None:
    assert scale_pixel_box(box=box, factor=factor) == expected


def test_scale_shape_resizes_a_mask_to_its_scaled_extent() -> None:
    mask = Shape(
        shape_type="mask",
        points=np.array([[1, 1], [2, 2]], dtype=np.float64),
        mask=np.array([[True, False], [False, False]]),
    )

    scaled = scale_shape(shape=mask, factor=(2.0, 2.0))

    np.testing.assert_array_equal(scaled.points, [[2, 2], [5, 5]])
    assert scaled.mask is not None
    assert scaled.mask.shape == (4, 4)
    assert scaled.mask[0, 0]
    assert not scaled.mask[3, 3]
    assert mask.mask is not None
    assert mask.mask.shape == (2, 2)


def test_scale_shape_stretches_a_circle_into_an_ellipse() -> None:
    circle = Shape(
        shape_type="circle",
        points=np.array([[40, 40], [48, 40]], dtype=np.float64),
    )

    scaled = scale_shape(shape=circle, factor=(0.5, 0.25))

    assert scaled.shape_type == "polygon"
    np.testing.assert_allclose(
        [scaled.points.min(axis=0), scaled.points.max(axis=0)],
        [[16, 8], [24, 12]],
    )


def test_scale_shape_keeps_every_mask_pixel_when_enlarging() -> None:
    mask = np.zeros((5, 5), dtype=bool)
    mask[0, 0] = mask[2, 2] = mask[4, 4] = True
    shape = Shape(
        shape_type="mask",
        points=np.array([[0, 0], [4, 4]], dtype=np.float64),
        mask=mask,
    )

    scaled = scale_shape(shape=shape, factor=(1.2, 1.2))

    assert scaled.mask is not None
    assert scaled.mask.shape == (6, 6)
    assert scaled.mask[2:4, 2:4].any()
    assert scaled.mask[0, 0] and scaled.mask[5, 5]


@pytest.mark.parametrize(
    "box", [(6, 6, 9, 9), (10, 20, 14, 24), (100, 100, 101, 101), (0, 0, 39, 9)]
)
def test_scale_shape_shrinks_a_rectangle_like_a_detection_box(
    box: tuple[int, int, int, int],
) -> None:
    rectangle = Shape(
        shape_type="rectangle",
        points=np.array([box[:2], box[2:]], dtype=np.float64),
    )

    shrunk = scale_shape(shape=rectangle, factor=(0.1, 0.25))

    np.testing.assert_array_equal(
        shrunk.points.ravel(), scale_pixel_box(box=box, factor=(0.1, 0.25))
    )
