from ._hit_testing import nearest_edge_index
from ._hit_testing import nearest_rotation_point_index
from ._hit_testing import nearest_vertex_index
from ._merge import can_merge_shapes
from ._merge import merge_masks
from ._model import CIRCLE_POINT_COUNT
from ._model import LINE_POINT_COUNT
from ._model import MIN_LINESTRIP_POINT_COUNT
from ._model import MIN_POLYGON_POINT_COUNT
from ._model import ORIENTED_RECTANGLE_POINT_COUNT
from ._model import POLYLINE_SHAPE_TYPES
from ._model import RECTANGLE_POINT_COUNT
from ._model import Shape
from ._model import ShapeType
from ._oriented_rectangle import get_rotation_handle
from ._oriented_rectangle import oriented_rectangle_arrow_points
from ._oriented_rectangle import oriented_rectangle_center
from ._oriented_rectangle import rotate

__all__ = [
    "CIRCLE_POINT_COUNT",
    "LINE_POINT_COUNT",
    "MIN_LINESTRIP_POINT_COUNT",
    "MIN_POLYGON_POINT_COUNT",
    "ORIENTED_RECTANGLE_POINT_COUNT",
    "POLYLINE_SHAPE_TYPES",
    "RECTANGLE_POINT_COUNT",
    "Shape",
    "ShapeType",
    "can_merge_shapes",
    "get_rotation_handle",
    "merge_masks",
    "nearest_edge_index",
    "nearest_rotation_point_index",
    "nearest_vertex_index",
    "oriented_rectangle_arrow_points",
    "oriented_rectangle_center",
    "rotate",
]
