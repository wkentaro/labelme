from __future__ import annotations

from fractions import Fraction

import numpy as np
import osam
import pytest

from labelme._automation._scaling import AtImageSize
from labelme._automation._scaling import Scale
from labelme._automation._scaling import scale_mask
from labelme._automation._scaling import scale_pixel_box
from labelme._automation._scaling import scale_shape
from labelme._shape import Shape


@pytest.mark.parametrize(
    ("box", "factor", "expected"),
    [
        ((0, 0, 0, 0), (Fraction(4), Fraction(2)), (0, 0, 3, 1)),
        ((8, 4, 23, 11), (Fraction(1, 4), Fraction(1, 2)), (2, 2, 5, 5)),
        ((5, 5, 5, 5), (Fraction(1, 10), Fraction(1, 10)), (0, 0, 0, 0)),
        ((-1, -1, -1, -1), (Fraction(1, 4), Fraction(1, 4)), (-1, -1, -1, -1)),
        ((0, 1023, 1023, 1023), (Fraction(1), Fraction(1, 2)), (0, 511, 1023, 511)),
        ((3, 1, 6, 1), (Fraction(1, 2), Fraction(3, 2)), (1, 1, 3, 2)),
        ((2, 0, 2, 0), (Fraction(1, 4), Fraction(1)), (0, 0, 0, 0)),
    ],
)
def test_scale_pixel_box_maps_whole_pixels(
    *,
    box: tuple[int, int, int, int],
    factor: Scale,
    expected: tuple[int, int, int, int],
) -> None:
    assert scale_pixel_box(box=box, factor=factor) == expected


def test_scale_shape_resizes_a_mask_to_its_scaled_extent() -> None:
    mask = Shape(
        shape_type="mask",
        points=np.array([[1, 1], [2, 2]], dtype=np.float64),
        mask=np.array([[True, False], [False, False]]),
    )

    scaled = scale_shape(shape=mask, factor=(Fraction(2), Fraction(2)))

    np.testing.assert_array_equal(scaled.points, [[2, 2], [5, 5]])
    assert scaled.mask is not None
    assert scaled.mask.shape == (4, 4)
    assert scaled.mask[0, 0]
    assert not scaled.mask[3, 3]
    assert mask.mask is not None
    assert mask.mask.shape == (2, 2)


def test_scale_shape_samples_a_mask_where_the_image_is_sampled() -> None:
    def mask_shape(*, xmin: int, width: int) -> Shape:
        mask = np.zeros((1, width), dtype=bool)
        mask[0, 14 - xmin : 17 - xmin] = True
        return Shape(
            shape_type="mask",
            points=np.array([[xmin, 0], [xmin + width - 1, 0]], dtype=np.float64),
            mask=mask,
        )

    padded = scale_shape(
        shape=mask_shape(xmin=0, width=18), factor=(Fraction(1, 10), Fraction(1, 10))
    )
    tight = scale_shape(
        shape=mask_shape(xmin=14, width=3), factor=(Fraction(1, 10), Fraction(1, 10))
    )

    np.testing.assert_array_equal(padded.points, [[0, 0], [1, 0]])
    np.testing.assert_array_equal(tight.points, [[1, 0], [1, 0]])
    assert padded.mask is not None and tight.mask is not None
    assert padded.mask.tolist() == [[False, True]]
    assert tight.mask.tolist() == [[True]]


def _mask_shape(*, xmin: int, ymin: int, mask: list[list[bool]]) -> Shape:
    array = np.array(mask, dtype=bool)
    height, width = array.shape
    return Shape(
        shape_type="mask",
        points=np.array(
            [[xmin, ymin], [xmin + width - 1, ymin + height - 1]], dtype=np.float64
        ),
        mask=array,
    )


@pytest.mark.parametrize(
    "factor", [Fraction(66_060_359, 1008), Fraction(1008, 66_060_359)]
)
def test_scale_shape_scales_a_mask_the_same_however_it_is_padded(
    factor: Fraction,
) -> None:
    def foreground_columns(*, mask: list[list[bool]]) -> list[int]:
        scaled = scale_shape(
            shape=_mask_shape(xmin=503, ymin=0, mask=mask), factor=(factor, Fraction(1))
        )
        assert scaled.mask is not None
        return (np.flatnonzero(scaled.mask[0]) + int(scaled.points[0, 0])).tolist()

    assert foreground_columns(mask=[[True]]) == foreground_columns(mask=[[True, False]])


def test_scale_shape_keeps_every_stripe_of_a_shrunk_mask() -> None:
    stripes = [[True], [False], [False], [False], [True]]

    scaled = scale_shape(
        shape=_mask_shape(xmin=0, ymin=2, mask=stripes),
        factor=(Fraction(1), Fraction(1, 2)),
    )

    assert scaled.mask is not None
    assert scaled.mask.tolist() == [[True], [False], [True]]
    np.testing.assert_array_equal(scaled.points, [[0, 1], [0, 3]])


def test_scale_shape_stretches_a_circle_into_an_ellipse() -> None:
    circle = Shape(
        shape_type="circle",
        points=np.array([[40, 40], [48, 40]], dtype=np.float64),
    )

    scaled = scale_shape(shape=circle, factor=(Fraction(1, 2), Fraction(1, 4)))

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

    scaled = scale_shape(shape=shape, factor=(Fraction(6, 5), Fraction(6, 5)))

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

    shrunk = scale_shape(shape=rectangle, factor=(Fraction(1, 10), Fraction(1, 4)))

    np.testing.assert_array_equal(
        shrunk.points.ravel(),
        scale_pixel_box(box=box, factor=(Fraction(1, 10), Fraction(1, 4))),
    )


@pytest.mark.parametrize(
    ("image_size", "sent_size", "box"),
    [
        ((4099, 4099), (1025, 1025), (1, 2, 4097, 4090)),
        ((10000, 504), (1008, 1008), (1, 2, 9997, 501)),
    ],
)
def test_pooled_mask_matches_pooling_the_mask_at_image_size(
    image_size: tuple[int, int],
    sent_size: tuple[int, int],
    box: tuple[int, int, int, int],
) -> None:
    at_image_size = AtImageSize(
        annotation=osam.types.Annotation(
            bounding_box=osam.types.BoundingBox(
                xmin=box[0], ymin=box[1], xmax=box[2], ymax=box[3]
            ),
            mask_scores=np.random.default_rng(0).integers(0, 256, (64, 64), np.uint8),
        ),
        image_size=image_size,
    )
    shrink = (
        Fraction(sent_size[0], image_size[0]),
        Fraction(sent_size[1], image_size[1]),
    )
    saved = at_image_size.mask()
    assert saved is not None

    _, expected = scale_mask(mask=saved, box=box, factor=shrink)

    np.testing.assert_array_equal(at_image_size.pooled_mask(factor=shrink), expected)
