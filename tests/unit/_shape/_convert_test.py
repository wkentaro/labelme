from __future__ import annotations

from typing import Final

import numpy as np
import pytest

from labelme._shape import ConvertBlocker
from labelme._shape import ConvertTarget
from labelme._shape import Shape
from labelme._shape import ShapeType
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
    circle = _shape(shape_type="circle", points=[[0, 0], [1, 1]])

    with pytest.raises(ValueError):
        convert_shape(shape=circle, target="polygon")


_POLYGON: Final = [[0, 0], [4, 0], [4, 4]]


@pytest.mark.parametrize(
    ("shapes", "target", "blocker"),
    [
        ([], "polygon", "no_selection"),
        (
            [_shape(shape_type="circle", points=[[0, 0], [1, 1]])],
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
            [_shape(shape_type="circle", points=[[0, 0], [1, 1]], locked=True)],
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
