from __future__ import annotations

from typing import Final

import numpy as np
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

    polygon = convert_shape(shape=rect, target="polygon")

    assert polygon.shape_type == "polygon"
    assert polygon.points.tolist() == [[1, 2], [5, 2], [5, 8], [1, 8]]
    assert polygon.point_labels.tolist() == [1, 1, 1, 1]


def test_polygon_to_rectangle_keeps_bounding_box() -> None:
    polygon = _shape(shape_type="polygon", points=[[3, 0], [6, 4], [0, 9]])

    rect = convert_shape(shape=polygon, target="rectangle")

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

    converted = convert_shape(shape=shape, target=target)

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
            [[11, 21], [13, 22]],
        ),
    ],
    ids=["circle", "oriented-rectangle", "linestrip", "mask-hugs-pixels"],
)
def test_bounding_box_from_any_area_kind(shape: Shape, box: list[list[int]]) -> None:
    rect = convert_shape(shape=shape, target="rectangle")

    assert rect.shape_type == "rectangle"
    assert rect.points.tolist() == box
    assert rect.mask is None


def test_bounding_box_stays_inside_the_given_image() -> None:
    circle = _shape(shape_type="circle", points=[[5, 64], [20, 64]])

    rect = convert_shape(shape=circle, target="rectangle", image_size=(128, 70))

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

    assert convert_shape(shape=shape, target=target).points.tolist() == points


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

    polygon = convert_shape(shape=rect, target="polygon")

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

    polygon = convert_shape(shape=circle, target="polygon", detail=60)

    assert polygon.shape_type == "polygon"
    assert polygon.point_labels.tolist() == [1] * len(polygon.points)


def test_circle_polygon_stays_inside_the_given_image() -> None:
    circle = _shape(shape_type="circle", points=[[5, 50], [20, 50]])

    polygon = convert_shape(
        shape=circle, target="polygon", image_size=(100, 100), detail=60
    )

    assert polygon.points.min() >= 0
    # The edges crossing x=0 end where they cross it, not at a clamped vertex.
    on_border = polygon.points[np.isclose(polygon.points[:, 0], 0)]
    np.testing.assert_allclose(sorted(on_border[:, 1]), [37.0711, 62.9289], atol=1e-4)


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
            polygon = convert_shape(
                shape=circle, target="polygon", image_size=(100, 100), detail=detail
            )
            assert len(np.unique(polygon.points, axis=0)) >= 3  # noqa: PLR2004


def test_circle_polygon_has_no_repeated_vertex_on_the_border() -> None:
    circle = _shape(shape_type="circle", points=[[50, 0], [60, 0]])

    polygon = convert_shape(
        shape=circle, target="polygon", image_size=(100, 100), detail=60
    )

    gaps = np.linalg.norm(polygon.points - np.roll(polygon.points, 1, axis=0), axis=1)
    assert gaps.min() > 1e-3  # noqa: PLR2004


def test_small_circle_far_from_the_origin_keeps_every_vertex() -> None:
    circle = _shape(shape_type="circle", points=[[3000, 3000], [3001, 3000]])

    polygon = convert_shape(
        shape=circle, target="polygon", image_size=(4000, 4000), detail=100
    )

    assert len(np.unique(polygon.points, axis=0)) == len(polygon.points) == 360  # noqa: PLR2004
