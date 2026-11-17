from __future__ import annotations

import tempfile
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any
from typing import Final

import numpy as np
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import array_shapes
from hypothesis.extra.numpy import arrays

from labelme._image_codec import img_arr_to_data
from labelme._label_file import _RESERVED_TOP_LEVEL_KEYS
from labelme._label_file import Annotation
from labelme._label_file import read_label_file
from labelme._label_file import write_label_file
from labelme._shape import CIRCLE_POINT_COUNT
from labelme._shape import LINE_POINT_COUNT
from labelme._shape import MIN_LINESTRIP_POINT_COUNT
from labelme._shape import MIN_POLYGON_POINT_COUNT
from labelme._shape import ORIENTED_RECTANGLE_POINT_COUNT
from labelme._shape import RECTANGLE_POINT_COUNT
from labelme._shape import ShapeDict

_JSON_VALUES: Final = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda children: (
        st.lists(children, max_size=3)
        | st.dictionaries(st.text(), children, max_size=3)
    ),
    max_leaves=5,
)


@st.composite
def _shapes(draw: st.DrawFn, *, width: int, height: int) -> ShapeDict:  # noqa: GR013 -- st.composite passes draw positionally
    MAX_POINT_COUNT: Final = 8
    POINT_COUNT_RANGE_BY_SHAPE_TYPE: Final[dict[str, tuple[int, int]]] = {
        "polygon": (MIN_POLYGON_POINT_COUNT, MAX_POINT_COUNT),
        "rectangle": (RECTANGLE_POINT_COUNT, RECTANGLE_POINT_COUNT),
        "oriented_rectangle": (
            ORIENTED_RECTANGLE_POINT_COUNT,
            ORIENTED_RECTANGLE_POINT_COUNT,
        ),
        "point": (1, 1),
        "line": (LINE_POINT_COUNT, LINE_POINT_COUNT),
        "circle": (CIRCLE_POINT_COUNT, CIRCLE_POINT_COUNT),
        "linestrip": (MIN_LINESTRIP_POINT_COUNT, MAX_POINT_COUNT),
        "points": (1, MAX_POINT_COUNT),
        "mask": (2, 2),
    }
    RESERVED_SHAPE_KEYS: Final = ShapeDict.__required_keys__ - {"other_data"}

    shape_type = draw(st.sampled_from(sorted(POINT_COUNT_RANGE_BY_SHAPE_TYPE)))
    min_point_count, max_point_count = POINT_COUNT_RANGE_BY_SHAPE_TYPE[shape_type]
    return ShapeDict(
        label=draw(st.text()),
        points=draw(
            st.lists(
                st.tuples(
                    st.floats(min_value=0, max_value=width),
                    st.floats(min_value=0, max_value=height),
                ).map(list),
                min_size=min_point_count,
                max_size=max_point_count,
            )
        ),
        shape_type=shape_type,
        flags=draw(st.dictionaries(st.text(), st.booleans(), max_size=3)),
        description=draw(st.text()),
        group_id=draw(st.none() | st.integers()),
        mask=draw(arrays(np.bool_, array_shapes(min_dims=2, max_dims=2)))
        if shape_type == "mask"
        else None,
        locked=draw(st.booleans()),
        other_data=draw(
            st.dictionaries(
                st.text().filter(lambda key: key not in RESERVED_SHAPE_KEYS),
                _JSON_VALUES,
                max_size=3,
            )
        ),
    )


def _comparable(*, shapes: list[ShapeDict]) -> list[dict[str, Any]]:
    return [
        {**shape, "mask": None if shape["mask"] is None else shape["mask"].tolist()}
        for shape in shapes
    ]


@settings(deadline=None)
@given(
    width=st.integers(min_value=1, max_value=32),
    height=st.integers(min_value=1, max_value=32),
    data=st.data(),
)
def test_read_label_file_returns_what_write_label_file_wrote(
    *, width: int, height: int, data: st.DataObject
) -> None:
    annotation = Annotation(
        image_path=data.draw(st.text()),
        image_data=img_arr_to_data(
            img_arr=np.zeros((height, width, 3), dtype=np.uint8)
        ),
        shapes=data.draw(st.lists(_shapes(width=width, height=height), max_size=5)),
        flags=data.draw(st.dictionaries(st.text(), st.booleans(), max_size=3)),
        other_data=data.draw(
            st.dictionaries(
                st.text().filter(lambda key: key not in _RESERVED_TOP_LEVEL_KEYS),
                _JSON_VALUES,
                max_size=3,
            )
        ),
    )

    with tempfile.TemporaryDirectory() as directory:
        filename = str(Path(directory) / "annotation.json")
        write_label_file(
            filename=filename,
            annotation=annotation,
            image_height=height,
            image_width=width,
            save_image_data=True,
        )
        loaded = read_label_file(filename=filename)

    assert loaded.image_path == PureWindowsPath(annotation.image_path).as_posix()
    assert loaded.image_data == annotation.image_data
    assert loaded.flags == annotation.flags
    assert loaded.other_data == annotation.other_data
    assert _comparable(shapes=loaded.shapes) == _comparable(shapes=annotation.shapes)
