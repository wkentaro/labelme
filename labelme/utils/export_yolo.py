# MIT License
# Copyright (c) Kentaro Wada

"""Utility functions for exporting LabelMe annotations to YOLO format."""

from __future__ import annotations

import json
import os
import pathlib


def shape_to_yolo_line(
    shape: dict,
    img_w: int,
    img_h: int,
    class_list: list[str],
) -> str | None:
    """Convert a single LabelMe shape dict to a YOLO annotation line.

    Supports ``rectangle`` (bounding-box) and ``polygon`` shape types.
    Returns ``None`` for unsupported shape types or unknown labels.

    Args:
        shape: A shape dict as stored in a LabelMe JSON file, containing
            at least ``"label"``, ``"shape_type"``, and ``"points"`` keys.
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        class_list: Ordered list of class names.  The index of the label
            in this list becomes the YOLO class id.

    Returns:
        A YOLO annotation line (``"<class_id> <cx> <cy> <w> <h>"`` for
        bounding-boxes, or ``"<class_id> <x1> <y1> … <xn> <yn>"`` for
        polygons), or ``None`` when the shape cannot be converted.
    """
    label = shape.get("label")
    if label not in class_list:
        return None

    class_id = class_list.index(label)
    points = shape.get("points", [])
    shape_type = shape.get("shape_type", "polygon")

    if shape_type == "rectangle":
        if len(points) != 2:
            return None
        (x0, y0), (x1, y1) = points
        x_min, x_max = min(x0, x1), max(x0, x1)
        y_min, y_max = min(y0, y1), max(y0, y1)
        cx = (x_min + x_max) / 2.0 / img_w
        cy = (y_min + y_max) / 2.0 / img_h
        bw = (x_max - x_min) / img_w
        bh = (y_max - y_min) / img_h
        # Clamp to [0, 1]
        cx = max(0.0, min(1.0, cx))
        cy = max(0.0, min(1.0, cy))
        bw = max(0.0, min(1.0, bw))
        bh = max(0.0, min(1.0, bh))
        return f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"

    elif shape_type == "polygon":
        if len(points) < 3:
            return None
        coords: list[str] = []
        for x, y in points:
            nx = max(0.0, min(1.0, x / img_w))
            ny = max(0.0, min(1.0, y / img_h))
            coords.append(f"{nx:.6f} {ny:.6f}")
        return f"{class_id} " + " ".join(coords)

    # circle, line, linestrip, point — not supported in YOLO format
    return None


def json_to_yolo_dir(
    json_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    class_list: list[str],
) -> list[str]:
    """Convert a single LabelMe JSON file to YOLO ``.txt`` annotation files.

    The output ``.txt`` file is written to *output_dir* with the same stem as
    *json_path* (e.g. ``image.json`` → ``<output_dir>/image.txt``).

    Args:
        json_path: Path to a LabelMe JSON annotation file.
        output_dir: Directory where the YOLO ``.txt`` file will be saved
            (created automatically if it does not exist).
        class_list: Ordered list of class names used to assign class ids.

    Returns:
        List of YOLO annotation lines written to the output file.  May be
        empty if no supported shapes exist in the JSON.

    Raises:
        FileNotFoundError: If *json_path* does not exist.
        ValueError: If the JSON file is missing required fields
            (``imageWidth`` / ``imageHeight`` / ``shapes``).
    """
    json_path = pathlib.Path(json_path)
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    img_w: int | None = data.get("imageWidth")
    img_h: int | None = data.get("imageHeight")
    shapes: list[dict] = data.get("shapes", [])

    if img_w is None or img_h is None:
        raise ValueError(
            f"Missing imageWidth/imageHeight in {json_path}. "
            "Cannot compute normalised coordinates."
        )
    if img_w <= 0 or img_h <= 0:
        raise ValueError(
            f"imageWidth and imageHeight must be positive, got "
            f"imageWidth={img_w}, imageHeight={img_h} in {json_path}."
        )

    lines: list[str] = []
    for shape in shapes:
        line = shape_to_yolo_line(shape, img_w, img_h, class_list)
        if line is not None:
            lines.append(line)

    out_file = output_dir / json_path.with_suffix(".txt").name
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")

    return lines
