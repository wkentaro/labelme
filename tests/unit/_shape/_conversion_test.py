from __future__ import annotations

import numpy as np
import pytest

from labelme._shape import Shape
from labelme._shape import ShapeType
from labelme._shape import convert_shape_geometry
from labelme._shape import get_intersection_conversion_targets
from labelme._shape import get_valid_conversion_targets


def make_test_shape(
    *,
    shape_type: ShapeType,
    points: list[list[float]],
    label: str = "object",
    group_id: int | None = 7,
    flags: dict[str, bool] | None = None,
    description: str | None = "sample description",
    locked: bool = False,
) -> Shape:
    return Shape(
        label=label,
        shape_type=shape_type,
        group_id=group_id,
        flags=flags or {"occluded": True},
        description=description,
        points=np.array(points, dtype=np.float64),
        locked=locked,
    )


def test_rectangle_to_polygon_yields_four_vertex_polygon() -> None:
    rect = make_test_shape(
        shape_type="rectangle",
        points=[[10.0, 20.0], [50.0, 80.0]],
        label="car",
    )

    poly = convert_shape_geometry(shape=rect, target_type="polygon")

    assert poly.shape_type == "polygon"
    assert poly.closed is True
    assert poly.points.tolist() == [
        [10.0, 20.0],
        [50.0, 20.0],
        [50.0, 80.0],
        [10.0, 80.0],
    ]
    assert len(poly.point_labels) == 4
    assert poly.label == "car"
    assert poly.group_id == 7
    assert poly.flags == {"occluded": True}
    assert poly.description == "sample description"


def test_polygon_to_rectangle_bounding_box() -> None:
    poly = make_test_shape(
        shape_type="polygon",
        points=[[15.0, 25.0], [45.0, 10.0], [60.0, 75.0], [5.0, 50.0]],
        label="dog",
    )

    rect = convert_shape_geometry(shape=poly, target_type="rectangle")

    assert rect.shape_type == "rectangle"
    assert rect.closed is True
    assert rect.points.tolist() == [[5.0, 10.0], [60.0, 75.0]]
    assert len(rect.point_labels) == 2
    assert rect.label == "dog"
    assert rect.group_id == 7
    assert rect.flags == {"occluded": True}
    assert rect.description == "sample description"


def test_polygon_to_linestrip_preserves_points() -> None:
    pts = [[10.0, 10.0], [20.0, 30.0], [40.0, 20.0]]
    poly = make_test_shape(shape_type="polygon", points=pts)

    line = convert_shape_geometry(shape=poly, target_type="linestrip")

    assert line.shape_type == "linestrip"
    assert line.points.tolist() == pts
    assert line.label == poly.label
    assert line.group_id == poly.group_id


def test_linestrip_to_polygon_requires_at_least_three_points() -> None:
    two_point_line = make_test_shape(
        shape_type="linestrip", points=[[0.0, 0.0], [10.0, 10.0]]
    )
    assert get_valid_conversion_targets(two_point_line) == set()
    with pytest.raises(ValueError, match="Cannot convert"):
        convert_shape_geometry(shape=two_point_line, target_type="polygon")

    three_point_line = make_test_shape(
        shape_type="linestrip",
        points=[[0.0, 0.0], [10.0, 10.0], [20.0, 0.0]],
    )
    assert get_valid_conversion_targets(three_point_line) == {"polygon"}
    poly = convert_shape_geometry(shape=three_point_line, target_type="polygon")
    assert poly.shape_type == "polygon"
    assert poly.closed is True
    assert poly.points.tolist() == [[0.0, 0.0], [10.0, 10.0], [20.0, 0.0]]


def test_locked_shape_has_no_conversion_targets() -> None:
    locked_poly = make_test_shape(
        shape_type="polygon",
        points=[[0.0, 0.0], [10.0, 10.0], [20.0, 0.0]],
        locked=True,
    )
    assert get_valid_conversion_targets(locked_poly) == set()


def test_non_polygon_family_shapes_have_no_conversion_targets() -> None:
    for st in ("circle", "line", "point", "mask", "oriented_rectangle"):
        s = make_test_shape(shape_type=st, points=[[0.0, 0.0], [1.0, 1.0]])
        assert get_valid_conversion_targets(s) == set()


def test_get_intersection_conversion_targets() -> None:
    poly1 = make_test_shape(
        shape_type="polygon", points=[[0.0, 0.0], [1.0, 2.0], [2.0, 0.0]]
    )
    poly2 = make_test_shape(
        shape_type="polygon", points=[[5.0, 5.0], [6.0, 7.0], [8.0, 5.0]]
    )
    rect1 = make_test_shape(shape_type="rectangle", points=[[0.0, 0.0], [1.0, 1.0]])
    line_3pts = make_test_shape(
        shape_type="linestrip", points=[[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]]
    )

    # Empty
    assert get_intersection_conversion_targets([]) == set()

    # All polygons
    assert get_intersection_conversion_targets([poly1, poly2]) == {
        "rectangle",
        "linestrip",
    }

    # All rectangles
    assert get_intersection_conversion_targets([rect1]) == {"polygon"}

    # Mixed rectangle and linestrip (3 points) -> both can convert to polygon
    assert get_intersection_conversion_targets([rect1, line_3pts]) == {"polygon"}

    # Mixed polygon and rectangle -> intersection is empty
    assert get_intersection_conversion_targets([poly1, rect1]) == set()
