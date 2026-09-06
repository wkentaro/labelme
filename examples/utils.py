#!/usr/bin/env python
"""Keep these helpers independent so example users can copy and adapt them on
their own schedule, separate from the application maintainers. Dependencies
stay limited to the standard library, NumPy, and Pillow to avoid requiring
the application or its GUI stack.
"""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import math
import uuid
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any
from typing import Final

import numpy as np
import PIL.Image
import PIL.ImageDraw
from numpy.typing import NDArray


@dataclasses.dataclass(frozen=True)
class LabeledImage:
    image_data: bytes
    shapes: list[dict[str, Any]]


def _read_image_bytes(record: dict[str, Any], /, *, json_dir: Path) -> bytes:
    embedded = record.get("imageData")
    if embedded is not None:
        return base64.b64decode(embedded)
    # imagePath may carry Windows-style separators even when read on a
    # different OS than the one that produced the annotation.
    relative_path = PureWindowsPath(record["imagePath"]).as_posix()
    return (json_dir / relative_path).read_bytes()


def _build_shape(shape: dict[str, Any], /) -> dict[str, Any]:
    raw_mask = shape.get("mask")
    return {
        "label": shape["label"],
        "points": shape["points"],
        "shape_type": shape.get("shape_type") or "polygon",
        "group_id": shape.get("group_id"),
        "flags": shape.get("flags") or {},
        "mask": None if raw_mask is None else img_b64_to_arr(raw_mask).astype(bool),
    }


def load_label_file(filename: str, /) -> LabeledImage:
    json_path = Path(filename)
    record = json.loads(json_path.read_text(encoding="utf-8"))
    return LabeledImage(
        image_data=_read_image_bytes(record, json_dir=json_path.parent),
        shapes=[_build_shape(shape) for shape in record["shapes"]],
    )


def img_data_to_arr(img_data: bytes, /) -> NDArray[np.uint8]:
    return np.array(PIL.Image.open(io.BytesIO(img_data)))


def decode_img_data_as_rgb(img_data: bytes, /) -> NDArray[np.uint8]:
    # Converting at the PIL level rather than on the decoded array resolves a
    # palette image against its palette instead of reading the indices as
    # intensities, and drops the alpha channel that JPEG cannot represent.
    return np.array(PIL.Image.open(io.BytesIO(img_data)).convert("RGB"))


def img_b64_to_arr(img_b64: str | bytes, /) -> NDArray[np.uint8]:
    return img_data_to_arr(base64.b64decode(img_b64))


def shape_to_mask(
    img_shape: tuple[int, ...],
    points: list[list[float]],
    /,
    *,
    shape_type: str | None = None,
    line_width: int = 10,
    point_size: int = 5,
) -> NDArray[np.bool_]:
    # Point counts each shape type's geometry is defined by.
    CIRCLE_POINT_COUNT: Final = 2
    LINE_POINT_COUNT: Final = 2
    RECTANGLE_POINT_COUNT: Final = 2
    ORIENTED_RECTANGLE_POINT_COUNT: Final = 4
    MIN_POLYGON_POINT_COUNT: Final = 3

    mask = PIL.Image.fromarray(np.zeros(img_shape[:2], dtype=np.uint8))
    draw = PIL.ImageDraw.Draw(mask)
    xy = [tuple(point) for point in points]
    if shape_type == "circle":
        assert len(xy) == CIRCLE_POINT_COUNT, (
            "Shape of shape_type=circle must have 2 points"
        )
        (cx, cy), (px, py) = xy
        d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2)
        draw.ellipse(((cx - d, cy - d), (cx + d, cy + d)), outline=1, fill=1)
    elif shape_type == "rectangle":
        assert len(xy) == RECTANGLE_POINT_COUNT, (
            "Shape of shape_type=rectangle must have 2 points"
        )
        (x0, y0), (x1, y1) = xy
        draw.rectangle(
            ((min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))),
            outline=1,
            fill=1,
        )
    elif shape_type == "line":
        assert len(xy) == LINE_POINT_COUNT, (
            "Shape of shape_type=line must have 2 points"
        )
        draw.line(xy=xy, fill=1, width=line_width)  # ty: ignore[invalid-argument-type]
    elif shape_type == "linestrip":
        # joint="curve" rounds the joints so wide lines have no notch at turns.
        draw.line(xy=xy, fill=1, width=line_width, joint="curve")  # ty: ignore[invalid-argument-type]
    elif shape_type == "point":
        assert len(xy) == 1, "Shape of shape_type=point must have 1 points"
        cx, cy = xy[0]
        r = point_size
        draw.ellipse(((cx - r, cy - r), (cx + r, cy + r)), outline=1, fill=1)
    elif shape_type == "oriented_rectangle":
        assert len(xy) == ORIENTED_RECTANGLE_POINT_COUNT, (
            "Shape of shape_type=oriented_rectangle must have 4 points"
        )
        draw.polygon(xy=xy, outline=1, fill=1)  # ty: ignore[invalid-argument-type]
    elif shape_type in [None, "polygon"]:
        assert len(xy) >= MIN_POLYGON_POINT_COUNT, (
            "Polygon must have points more than 2"
        )
        draw.polygon(xy=xy, outline=1, fill=1)  # ty: ignore[invalid-argument-type]
    else:
        raise ValueError(f"shape_type={shape_type!r} is not supported.")
    return np.array(mask, dtype=bool)


def shapes_to_label(
    *,
    img_shape: tuple[int, ...],
    shapes: list[dict[str, Any]],
    label_name_to_value: dict[str, int],
) -> tuple[NDArray[np.int32], NDArray[np.int32]]:
    unknown = {s["label"] for s in shapes} - label_name_to_value.keys()
    if unknown:
        raise ValueError(
            f"shape labels not in the provided labels: {sorted(unknown)!r}; "
            f"add them so every shape label has a value"
        )

    cls = np.zeros(img_shape[:2], dtype=np.int32)
    ins = np.zeros_like(cls)
    instances: list[tuple[str, Any]] = []
    for shape in shapes:
        points = shape["points"]
        label = shape["label"]
        group_id = shape.get("group_id")
        if group_id is None:
            group_id = uuid.uuid1()
        shape_type = shape.get("shape_type")

        instance = (label, group_id)
        if instance not in instances:
            instances.append(instance)
        ins_id = instances.index(instance) + 1
        cls_id = label_name_to_value[label]

        mask: NDArray[np.bool_]
        if shape_type == "mask":
            if not isinstance(shape["mask"], np.ndarray):
                raise ValueError("shape['mask'] must be numpy.ndarray")
            mask = np.zeros(img_shape[:2], dtype=bool)
            point_array = np.asarray(points)
            (x1, y1), (x2, y2) = point_array.round().astype(int)
            # Integer bounds retain legacy cropping, while fractional bounds use
            # the stored extent so independently rounded corners cannot resize it.
            if np.array_equal(point_array, np.trunc(point_array)):
                patch_height, patch_width = y2 - y1 + 1, x2 - x1 + 1
            else:
                patch_height, patch_width = shape["mask"].shape
            height, width = img_shape[:2]
            y_start, y_stop = max(y1, 0), min(y1 + patch_height, height)
            x_start, x_stop = max(x1, 0), min(x1 + patch_width, width)
            if y_start < y_stop and x_start < x_stop:
                mask[y_start:y_stop, x_start:x_stop] = shape["mask"][
                    y_start - y1 : y_stop - y1, x_start - x1 : x_stop - x1
                ]
        else:
            mask = shape_to_mask(img_shape[:2], points, shape_type=shape_type)

        cls[mask] = cls_id
        ins[mask] = ins_id

    return cls, ins
