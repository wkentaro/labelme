from __future__ import annotations

from typing import Final

import numpy as np
import PIL.Image
import PIL.ImageDraw
import pytest

from labelme._shape import ConvertBlocker
from labelme._shape import ConvertTarget
from labelme._shape import Shape
from labelme._shape import ShapeType
from labelme._shape import conversion_needs_detail
from labelme._shape import convert_blocker
from labelme._shape import convert_shape


def _shape(
    *, shape_type: ShapeType, points: list[list[int]], locked: bool = False
) -> Shape:
    return Shape(shape_type=shape_type, points=np.array(points), locked=locked)


def test_rectangle_to_polygon_lists_corners_clockwise() -> None:
    rect = _shape(shape_type="rectangle", points=[[1, 2], [5, 8]])

    (polygon,) = convert_shape(shape=rect, target="polygon")

    assert polygon.shape_type == "polygon"
    assert polygon.points.tolist() == [[1, 2], [5, 2], [5, 8], [1, 8]]
    assert polygon.point_labels.tolist() == [1, 1, 1, 1]


def test_polygon_to_rectangle_keeps_bounding_box() -> None:
    polygon = _shape(shape_type="polygon", points=[[3, 0], [6, 4], [0, 9]])

    (rect,) = convert_shape(shape=polygon, target="rectangle")

    assert rect.shape_type == "rectangle"
    assert rect.points.tolist() == [[0, 0], [6, 9]]
    assert rect.point_labels.tolist() == [1, 1]


@pytest.mark.parametrize(
    ("source", "target"), [("polygon", "linestrip"), ("linestrip", "polygon")]
)
def test_polygon_linestrip_keeps_vertices(
    source: ShapeType, target: ConvertTarget
) -> None:
    shape = Shape(
        shape_type=source,
        points=np.array([[0, 0], [4, 0], [4, 4]]),
        point_labels=np.array([1, 0, 1]),
    )

    (converted,) = convert_shape(shape=shape, target=target)

    assert converted.shape_type == target
    assert converted.points.tolist() == [[0, 0], [4, 0], [4, 4]]
    assert converted.point_labels.tolist() == [1, 0, 1]


@pytest.mark.parametrize(
    ("shape", "box"),
    [
        (_shape(shape_type="circle", points=[[5, 5], [8, 9]]), [[0, 0], [10, 10]]),
        (
            _shape(
                shape_type="oriented_rectangle", points=[[2, 0], [4, 2], [2, 4], [0, 2]]
            ),
            [[0, 0], [4, 4]],
        ),
        (
            _shape(shape_type="linestrip", points=[[0, 3], [2, 0], [5, 4]]),
            [[0, 0], [5, 4]],
        ),
        (
            Shape(
                shape_type="mask",
                points=np.array([[10, 20], [14, 23]]),
                mask=np.array(
                    [
                        [0, 0, 0, 0, 0],
                        [0, 1, 1, 0, 0],
                        [0, 0, 1, 1, 0],
                        [0, 0, 0, 0, 0],
                    ],
                    dtype=bool,
                ),
            ),
            [[11, 21], [14, 23]],
        ),
    ],
    ids=["circle", "oriented-rectangle", "linestrip", "mask-hugs-pixels"],
)
def test_bounding_box_from_any_area_kind(shape: Shape, box: list[list[int]]) -> None:
    (rect,) = convert_shape(shape=shape, target="rectangle")

    assert rect.shape_type == "rectangle"
    assert rect.points.tolist() == box
    assert rect.mask is None


def test_bounding_box_stays_inside_the_given_image() -> None:
    circle = _shape(shape_type="circle", points=[[5, 64], [20, 64]])

    (rect,) = convert_shape(shape=circle, target="rectangle", image_size=(128, 70))

    assert rect.points.tolist() == [[0, 49], [20, 70]]


def test_bounding_box_outside_the_image_has_no_area() -> None:
    circle = _shape(shape_type="circle", points=[[150, 50], [160, 50]])

    assert (
        convert_blocker(shapes=[circle], target="rectangle", image_size=(100, 100))
        == "no_area"
    )


@pytest.mark.parametrize(
    ("source", "target", "points"),
    [
        ("line", "linestrip", [[0, 0], [4, 4]]),
        ("linestrip", "line", [[0, 0], [4, 4]]),
        ("oriented_rectangle", "polygon", [[2, 0], [4, 2], [2, 4], [0, 2]]),
    ],
)
def test_vertex_preserving_routes_keep_points(
    source: ShapeType, target: ConvertTarget, points: list[list[int]]
) -> None:
    shape = _shape(shape_type=source, points=points)

    assert convert_shape(shape=shape, target=target)[0].points.tolist() == points


def test_convert_keeps_identity_and_leaves_source_alone() -> None:
    rect = Shape(
        shape_type="rectangle",
        points=np.array([[0, 0], [2, 2]]),
        label="cat",
        group_id=3,
        flags={"occluded": True},
        description="left",
        other_data={"score": 0.9},
    )

    (polygon,) = convert_shape(shape=rect, target="polygon")

    assert (polygon.label, polygon.group_id, polygon.description) == ("cat", 3, "left")
    assert polygon.flags == {"occluded": True}
    assert polygon.other_data == {"score": 0.9}
    assert polygon.flags is not rect.flags
    assert rect.shape_type == "rectangle"
    assert rect.points.tolist() == [[0, 0], [2, 2]]


def test_convert_refuses_blocked_shape() -> None:
    point = _shape(shape_type="point", points=[[0, 0]])

    with pytest.raises(ValueError):
        convert_shape(shape=point, target="polygon")


_POLYGON: Final = [[0, 0], [4, 0], [4, 4]]


@pytest.mark.parametrize(
    ("shapes", "target", "blocker"),
    [
        ([], "polygon", "no_selection"),
        (
            [_shape(shape_type="point", points=[[0, 0]])],
            "polygon",
            "wrong_type",
        ),
        (
            [_shape(shape_type="polygon", points=_POLYGON)],
            "polygon",
            "already_target",
        ),
        (
            [_shape(shape_type="polygon", points=_POLYGON)],
            "circle",
            "wrong_type",
        ),
        (
            [
                _shape(shape_type="rectangle", points=[[0, 0], [1, 1]]),
                _shape(shape_type="polygon", points=_POLYGON, locked=True),
            ],
            "polygon",
            None,
        ),
        (
            [_shape(shape_type="linestrip", points=[[0, 0], [1, 1]])],
            "polygon",
            "too_few_points",
        ),
        (
            [_shape(shape_type="linestrip", points=[[0, 0], [5, 5], [0, 0]])],
            "polygon",
            "too_few_points",
        ),
        (
            [_shape(shape_type="polygon", points=_POLYGON, locked=True)],
            "rectangle",
            "locked",
        ),
        (
            [_shape(shape_type="linestrip", points=[[0, 0], [1, 1], [2, 0]])],
            "line",
            "too_many_points",
        ),
        (
            [_shape(shape_type="linestrip", points=[[0, 0], [1, 1], [0, 0]])],
            "line",
            "too_many_points",
        ),
        (
            [_shape(shape_type="linestrip", points=[[0, 0], [1, 1], [2, 2]])],
            "rectangle",
            None,
        ),
        (
            [_shape(shape_type="linestrip", points=[[0, 0], [0, 1], [0, 2]])],
            "rectangle",
            "no_area",
        ),
        (
            [_shape(shape_type="point", points=[[0, 0]])],
            "rectangle",
            "wrong_type",
        ),
        (
            [_shape(shape_type="point", points=[[0, 0]], locked=True)],
            "polygon",
            "wrong_type",
        ),
        (
            [
                _shape(shape_type="rectangle", points=[[0, 0], [1, 1]]),
                _shape(shape_type="linestrip", points=_POLYGON),
            ],
            "polygon",
            None,
        ),
        ([_shape(shape_type="polygon", points=_POLYGON)], "linestrip", None),
    ],
    ids=[
        "empty",
        "wrong-type",
        "already-target",
        "unsupported-target",
        "mixed-with-locked-target",
        "short-linestrip",
        "revisiting-linestrip",
        "locked",
        "long-linestrip-to-line",
        "revisiting-linestrip-to-line",
        "diagonal-linestrip-to-rectangle",
        "flat-linestrip-to-rectangle",
        "point-to-rectangle",
        "locked-wrong-type",
        "rectangle-and-linestrip",
        "polygon-to-linestrip",
    ],
)
def test_convert_blocker_names_first_failing_condition(
    *, shapes: list[Shape], target: ConvertTarget, blocker: ConvertBlocker | None
) -> None:
    assert convert_blocker(shapes=shapes, target=target) == blocker


def test_circle_to_polygon_needs_detail() -> None:
    circle = _shape(shape_type="circle", points=[[0, 0], [10, 0]])
    rect = _shape(shape_type="rectangle", points=[[0, 0], [2, 2]])

    assert conversion_needs_detail(shapes=[rect, circle], target="polygon")
    assert not conversion_needs_detail(shapes=[rect], target="polygon")
    assert not conversion_needs_detail(shapes=[circle], target="rectangle")
    with pytest.raises(ValueError):
        convert_shape(shape=circle, target="polygon")

    (polygon,) = convert_shape(shape=circle, target="polygon", detail=60)

    assert polygon.shape_type == "polygon"
    assert polygon.point_labels.tolist() == [1] * len(polygon.points)


def test_circle_polygon_stays_inside_the_given_image() -> None:
    circle = _shape(shape_type="circle", points=[[5, 50], [20, 50]])

    (polygon,) = convert_shape(
        shape=circle, target="polygon", image_size=(100, 100), detail=60
    )

    assert polygon.points.min() >= 0
    # The edges crossing x=0 end where they cross it, not at a clamped vertex.
    on_border = polygon.points[np.isclose(polygon.points[:, 0], 0)]
    np.testing.assert_allclose(sorted(on_border[:, 1]), [36.0183, 63.9817], atol=1e-4)


def test_zero_radius_circle_has_no_polygon_even_unclipped() -> None:
    circle = _shape(shape_type="circle", points=[[50, 50], [50, 50]])

    assert convert_blocker(shapes=[circle], target="polygon") == "no_area"


@pytest.mark.parametrize(
    ("points", "blocker"),
    [
        ([[-14, -14], [6, -14]], None),
        ([[-15, -15], [6, -15]], "no_area"),
        ([[-10, 50], [5, 50]], None),
        ([[-19, 50], [1, 50]], None),
        ([[200, 50], [210, 50]], "no_area"),
    ],
    ids=["corner-graze", "corner-miss", "overhang", "sliver", "outside"],
)
def test_circle_polygon_needs_an_area_inside_the_image(
    points: list[list[int]], blocker: ConvertBlocker | None
) -> None:
    circle = _shape(shape_type="circle", points=points)

    assert (
        convert_blocker(shapes=[circle], target="polygon", image_size=(100, 100))
        == blocker
    )
    if blocker is None:
        for detail in range(0, 101, 10):
            (polygon,) = convert_shape(
                shape=circle, target="polygon", image_size=(100, 100), detail=detail
            )
            assert len(np.unique(polygon.points, axis=0)) >= 3  # noqa: PLR2004


def test_circle_polygon_has_no_repeated_vertex_on_the_border() -> None:
    circle = _shape(shape_type="circle", points=[[50, 0], [60, 0]])

    (polygon,) = convert_shape(
        shape=circle, target="polygon", image_size=(100, 100), detail=60
    )

    gaps = np.linalg.norm(polygon.points - np.roll(polygon.points, 1, axis=0), axis=1)
    assert gaps.min() > 1e-3  # noqa: PLR2004


def test_small_circle_far_from_the_origin_keeps_every_vertex() -> None:
    circle = _shape(shape_type="circle", points=[[3000, 3000], [3001, 3000]])

    (polygon,) = convert_shape(
        shape=circle, target="polygon", image_size=(4000, 4000), detail=100
    )

    assert len(np.unique(polygon.points, axis=0)) == len(polygon.points) == 360  # noqa: PLR2004


def test_mask_becomes_one_polygon_per_land() -> None:
    pixels = np.zeros((20, 40), dtype=bool)
    pixels[2:18, 2:15] = True
    pixels[2:18, 25:38] = True
    mask = Shape(
        label="cells",
        group_id=7,
        shape_type="mask",
        points=np.array([[100, 50], [139, 69]]),
        mask=pixels,
    )

    assert conversion_needs_detail(shapes=[mask], target="polygon")
    polygons = convert_shape(shape=mask, target="polygon", detail=60)

    assert [(p.shape_type, p.label, p.group_id) for p in polygons] == [
        ("polygon", "cells", 7)
    ] * 2
    assert all(p.mask is None for p in polygons)
    # Each land stays where it was in the image, not in the mask's frame.
    lefts = sorted(p.points[:, 0].min() for p in polygons)
    np.testing.assert_allclose(lefts, [102, 125], atol=0.5)


def test_mask_too_thin_for_the_detail_keeps_its_outline() -> None:
    mask = Shape(
        shape_type="mask",
        points=np.array([[0, 0], [4, 0]]),
        mask=np.ones((1, 5), dtype=bool),
    )

    (polygon,) = convert_shape(shape=mask, target="polygon", detail=0)

    assert len(polygon.points) >= 3  # noqa: PLR2004


def test_empty_mask_has_no_polygon() -> None:
    mask = Shape(
        shape_type="mask",
        points=np.array([[0, 0], [3, 3]]),
        mask=np.zeros((4, 4), dtype=bool),
    )

    assert convert_blocker(shapes=[mask], target="polygon") == "no_area"


def test_polygon_becomes_a_mask_of_the_pixels_it_covers() -> None:
    square = _shape(shape_type="polygon", points=[[2, 3], [6, 3], [6, 7], [2, 7]])

    assert not conversion_needs_detail(shapes=[square], target="mask")
    (mask,) = convert_shape(shape=square, target="mask")

    assert mask.shape_type == "mask"
    assert mask.points.tolist() == [[2, 3], [6, 7]]
    assert mask.mask is not None
    assert mask.mask.shape == (5, 5)
    assert mask.mask.all()


def test_polygon_mask_is_clipped_to_the_image() -> None:
    overhang = _shape(shape_type="polygon", points=[[-5, -5], [5, -5], [5, 5]])
    outside = _shape(shape_type="polygon", points=[[-9, -9], [-5, -9], [-5, -5]])

    (mask,) = convert_shape(shape=overhang, target="mask", image_size=(100, 100))

    assert mask.points.tolist() == [[0, 0], [5, 5]]
    assert (
        convert_blocker(shapes=[outside], target="mask", image_size=(100, 100))
        == "no_area"
    )
    # The image starts at 0 even when its size is not given.
    assert convert_blocker(shapes=[outside], target="mask") == "no_area"


def test_polygon_mask_keeps_every_pixel_a_fractional_polygon_covers() -> None:
    square = Shape(
        shape_type="polygon",
        points=np.array([[2.7, 3.7], [6.7, 3.7], [6.7, 7.7], [2.7, 7.7]]),
    )
    image = PIL.Image.new("L", (20, 20), 0)
    PIL.ImageDraw.Draw(image).polygon([tuple(p) for p in square.points], fill=1)

    (mask,) = convert_shape(shape=square, target="mask")

    assert mask.points.dtype == np.float64
    assert mask.mask is not None
    assert mask.mask.sum() == np.asarray(image).sum()


def test_mask_polygons_stay_inside_the_image() -> None:
    def mask_at(x: int) -> Shape:
        return Shape(
            shape_type="mask",
            points=np.array([[x, 10], [x + 9, 19]]),
            mask=np.ones((10, 10), dtype=bool),
        )

    (polygon,) = convert_shape(
        shape=mask_at(95), target="polygon", image_size=(100, 100), detail=100
    )

    assert polygon.points[:, 0].max() <= 100  # noqa: PLR2004
    assert (
        convert_blocker(shapes=[mask_at(105)], target="polygon", image_size=(100, 100))
        == "no_area"
    )


def test_polygon_mask_matches_image_rasterization_past_the_border() -> None:
    triangle = Shape(
        shape_type="polygon", points=np.array([[-0.4, 0.0], [2.0, 2.0], [0.0, 4.0]])
    )
    image = PIL.Image.new("L", (8, 8), 0)
    PIL.ImageDraw.Draw(image).polygon([tuple(p) for p in triangle.points], fill=1)

    (mask,) = convert_shape(shape=triangle, target="mask")

    assert mask.mask is not None
    x0, y0 = mask.points[0].astype(int)
    inside = mask.mask[-y0 if y0 < 0 else 0 :, -x0 if x0 < 0 else 0 :]
    assert inside.sum() == np.asarray(image).sum()


def test_converted_polygons_are_closed_and_inside_the_image() -> None:
    mask = Shape(
        shape_type="mask",
        points=np.array([[-0.25, 0.0], [8.75, 9.0]]),
        mask=np.ones((10, 10), dtype=bool),
        closed=False,
    )

    (polygon,) = convert_shape(
        shape=mask, target="polygon", image_size=(10, 10), detail=100
    )

    assert polygon.closed
    assert polygon.points.min() >= 0


def test_polygon_mask_matches_image_rasterization_pixel_for_pixel() -> None:
    triangle = _shape(shape_type="polygon", points=[[12, 1], [2, 13], [1, 7]])
    image = PIL.Image.new("L", (20, 20), 0)
    PIL.ImageDraw.Draw(image).polygon([tuple(p) for p in triangle.points], fill=1)

    (mask,) = convert_shape(shape=triangle, target="mask", image_size=(20, 20))

    assert mask.mask is not None
    (x0, y0), (x1, y1) = mask.points.astype(int)
    expected = np.asarray(image, dtype=bool)
    np.testing.assert_array_equal(mask.mask, expected[y0 : y1 + 1, x0 : x1 + 1])
    assert mask.mask.sum() == expected.sum()


def test_conversions_that_would_leave_nothing_are_blocked() -> None:
    corner_pixel = np.zeros((2, 2), dtype=bool)
    corner_pixel[0, 0] = True
    mask = Shape(
        shape_type="mask",
        points=np.array([[-1.0, -1.0], [0.0, 0.0]]),
        mask=corner_pixel,
    )
    on_border = _shape(shape_type="polygon", points=[[10, 2], [10, 3], [10, 4]])
    # Pixel centers on the bottom border trace outlines that run below it.
    bottom_row = Shape(
        shape_type="mask",
        points=np.array([[3.0, 10.0], [4.0, 10.0]]),
        mask=np.ones((1, 2), dtype=bool),
    )

    assert (
        convert_blocker(shapes=[mask], target="polygon", image_size=(10, 10))
        == "no_area"
    )
    assert (
        convert_blocker(shapes=[on_border], target="mask", image_size=(10, 10))
        == "no_area"
    )
    assert (
        convert_blocker(shapes=[bottom_row], target="polygon", image_size=(10, 10))
        == "no_area"
    )


def test_polygon_mask_never_outgrows_the_image() -> None:
    huge = _shape(
        shape_type="polygon", points=[[0, 0], [4096, 0], [4096, 4096], [0, 4096]]
    )

    (mask,) = convert_shape(shape=huge, target="mask", image_size=(10, 10))

    assert mask.mask is not None
    assert mask.mask.shape == (10, 10)
    assert mask.mask.base is None


def test_polygon_mask_past_the_top_left_matches_image_rasterization() -> None:
    triangle = _shape(shape_type="polygon", points=[[-2, 6], [2, 1], [7, 0]])
    image = PIL.Image.new("L", (8, 8), 0)
    PIL.ImageDraw.Draw(image).polygon([tuple(p) for p in triangle.points], fill=1)

    (mask,) = convert_shape(shape=triangle, target="mask", image_size=(8, 8))

    assert mask.mask is not None
    (x0, y0), (x1, y1) = mask.points.astype(int)
    expected = np.asarray(image, dtype=bool)
    np.testing.assert_array_equal(mask.mask, expected[y0 : y1 + 1, x0 : x1 + 1])
    assert mask.mask.sum() == expected.sum()


def test_mask_at_a_fractional_origin_keeps_lands_that_fit() -> None:
    pixels = np.zeros((1, 10), dtype=bool)
    pixels[0, [0, 9]] = True
    mask = Shape(
        shape_type="mask", points=np.array([[0.25, 4.0], [9.25, 4.0]]), mask=pixels
    )

    polygons = convert_shape(
        shape=mask, target="polygon", image_size=(10, 10), detail=100
    )

    assert len(polygons) == 2  # noqa: PLR2004
    assert all(p.points.max() <= 10 for p in polygons)  # noqa: PLR2004


def test_mask_land_partly_inside_the_image_is_kept() -> None:
    pixels = np.zeros((1, 10), dtype=bool)
    pixels[0, [0, 9]] = True
    mask = Shape(
        shape_type="mask", points=np.array([[0.75, 4.0], [9.75, 4.0]]), mask=pixels
    )

    polygons = convert_shape(
        shape=mask, target="polygon", image_size=(10, 10), detail=100
    )

    assert len(polygons) == 2  # noqa: PLR2004
    assert all(p.points.max() <= 10 for p in polygons)  # noqa: PLR2004


@pytest.mark.parametrize(
    ("origin", "pixels"),
    [
        ([-0.25, 4.0], [[1], [1]]),
        ([-0.75, 7.5], [[1, 0, 0], [1, 1, 1]]),
    ],
    ids=["column-past-the-left", "diagonal-edge-into-the-corner"],
)
def test_mask_outline_reaching_into_the_image_converts(
    origin: list[float], pixels: list[list[int]]
) -> None:
    mask = Shape(
        shape_type="mask",
        points=np.array([origin, origin]),
        mask=np.array(pixels, dtype=bool),
    )

    assert convert_blocker(shapes=[mask], target="polygon", image_size=(8, 8)) is None
    assert convert_shape(shape=mask, target="polygon", image_size=(8, 8), detail=60)
