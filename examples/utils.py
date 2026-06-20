#!/usr/bin/env python
"""Self-contained helpers for reading the labelme JSON annotation format.

labelme is an application, not a Python library: the supported way to consume
its output is to read the JSON format yourself, the way a PyTorch ``Dataset``
reads whatever format its data lives in. This module is the worked reference for
doing that. It depends only on the standard library, numpy, and PIL, never on
``labelme``, so it keeps working regardless of how labelme's internals evolve.

It deliberately re-implements the rasterization helpers (``shape_to_mask``,
``shapes_to_label``, ``img_data_to_arr``) rather than importing them: this copy
and labelme's internal copy have different owners and lifecycles. Copy this file
next to your own scripts and adapt it.
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

import numpy as np
import PIL.Image
import PIL.ImageDraw
from numpy.typing import NDArray


@dataclasses.dataclass(frozen=True)
class LabeledImage:
    image_data: bytes
    shapes: list[dict[str, Any]]


def load_label_file(filename: str) -> LabeledImage:
    with open(filename, encoding="utf-8") as f:
        data = json.load(f)

    if data.get("imageData") is not None:
        image_data = base64.b64decode(data["imageData"])
    else:
        image_path = PureWindowsPath(data["imagePath"]).as_posix()
        image_data = (Path(filename).parent / image_path).read_bytes()

    shapes = [
        {
            "label": shape["label"],
            "points": shape["points"],
            "shape_type": shape.get("shape_type") or "polygon",
            "group_id": shape.get("group_id"),
            "flags": shape.get("flags") or {},
            "mask": None
            if shape.get("mask") is None
            else img_b64_to_arr(shape["mask"]).astype(bool),
        }
        for shape in data["shapes"]
    ]
    return LabeledImage(image_data=image_data, shapes=shapes)


def img_data_to_arr(img_data: bytes) -> NDArray[np.uint8]:
    return np.array(PIL.Image.open(io.BytesIO(img_data)))


def img_b64_to_arr(img_b64: str | bytes) -> NDArray[np.uint8]:
    return img_data_to_arr(base64.b64decode(img_b64))


def shape_to_mask(
    img_shape: tuple[int, ...],
    points: list[list[float]],
    shape_type: str | None = None,
    line_width: int = 10,
    point_size: int = 5,
) -> NDArray[np.bool_]:
    mask = PIL.Image.fromarray(np.zeros(img_shape[:2], dtype=np.uint8))
    draw = PIL.ImageDraw.Draw(mask)
    xy = [tuple(point) for point in points]
    if shape_type == "circle":
        assert len(xy) == 2, "Shape of shape_type=circle must have 2 points"
        (cx, cy), (px, py) = xy
        d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2)
        draw.ellipse(((cx - d, cy - d), (cx + d, cy + d)), outline=1, fill=1)
    elif shape_type == "rectangle":
        assert len(xy) == 2, "Shape of shape_type=rectangle must have 2 points"
        (x0, y0), (x1, y1) = xy
        draw.rectangle(
            ((min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))),
            outline=1,
            fill=1,
        )
    elif shape_type == "line":
        assert len(xy) == 2, "Shape of shape_type=line must have 2 points"
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
        assert len(xy) == 4, "Shape of shape_type=oriented_rectangle must have 4 points"
        draw.polygon(xy=xy, outline=1, fill=1)  # ty: ignore[invalid-argument-type]
    elif shape_type in [None, "polygon"]:
        assert len(xy) > 2, "Polygon must have points more than 2"
        draw.polygon(xy=xy, outline=1, fill=1)  # ty: ignore[invalid-argument-type]
    else:
        raise ValueError(f"shape_type={shape_type!r} is not supported.")
    return np.array(mask, dtype=bool)


def shapes_to_label(
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
            (x1, y1), (x2, y2) = np.asarray(points).astype(int)
            mask[y1 : y2 + 1, x1 : x2 + 1] = shape["mask"]
        else:
            mask = shape_to_mask(img_shape[:2], points, shape_type)

        cls[mask] = cls_id
        ins[mask] = ins_id

    return cls, ins
