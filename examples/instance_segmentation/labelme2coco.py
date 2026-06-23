#!/usr/bin/env python

import argparse
import collections
import datetime
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any
from typing import Final

import imgviz
import numpy as np

try:
    import pycocotools.mask  # type: ignore
except ImportError:
    print("Please install pycocotools:\n\n    pip install pycocotools\n")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import utils  # noqa: E402  # examples/utils.py, vendored alongside this script


def _circle_to_polygon_segmentation(
    *, center: tuple[float, float], edge: tuple[float, float]
) -> list[float]:
    CHORD_TOLERANCE_PX: Final = 1.0
    MIN_VERTICES: Final = 12

    cx, cy = center
    ex, ey = edge
    radius = math.hypot(ex - cx, ey - cy)
    if radius == 0.0:
        raise ValueError("Degenerate circle: center and edge are the same point.")

    # Pick a vertex count so the chord-to-arc deviation stays within 1 pixel:
    # solving r * (1 - cos(pi / n)) <= tol for n yields n >= pi / acos(1 - tol/r).
    # When r <= tol the formula domain breaks, so clamp to the minimum.
    if radius <= CHORD_TOLERANCE_PX:
        n_vertices = MIN_VERTICES
    else:
        n_vertices = max(
            MIN_VERTICES,
            int(math.pi / math.acos(1.0 - CHORD_TOLERANCE_PX / radius)),
        )
    angles = (2.0 * math.pi / n_vertices) * np.arange(n_vertices)
    coords = np.empty((n_vertices, 2), dtype=float)
    coords[:, 0] = cx + radius * np.cos(angles)
    coords[:, 1] = cy + radius * np.sin(angles)
    return coords.flatten().tolist()


def main() -> None:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("input_dir", help="input annotated directory")
    parser.add_argument("output_dir", help="output dataset directory")
    parser.add_argument("--labels", help="labels file", required=True)
    parser.add_argument("--noviz", help="no visualization", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        print("Output directory already exists:", output_dir)
        sys.exit(1)
    output_dir.mkdir(parents=True)
    (output_dir / "JPEGImages").mkdir(parents=True)
    if not args.noviz:
        (output_dir / "Visualization").mkdir(parents=True)
    print("Creating dataset:", output_dir)

    now = datetime.datetime.now()

    data: dict[str, Any] = dict(
        info=dict(
            description=None,
            url=None,
            version=None,
            year=now.year,
            contributor=None,
            date_created=now.strftime("%Y-%m-%d %H:%M:%S.%f"),
        ),
        licenses=[
            dict(
                url=None,
                id=0,
                name=None,
            )
        ],
        type="instances",
    )
    data["images"] = []  # license, url, file_name, height, width, date_captured, id
    data["categories"] = []  # supercategory, id, name
    data[
        "annotations"
    ] = []  # segmentation, area, iscrowd, image_id, bbox, category_id, id

    class_name_to_id = {}
    for i, line in enumerate(open(args.labels).readlines()):
        class_id = i - 1  # starts with -1
        class_name = line.strip()
        if class_id == -1:
            assert class_name == "__ignore__"
            continue
        class_name_to_id[class_name] = class_id
        data["categories"].append(
            dict(
                supercategory=None,
                id=class_id,
                name=class_name,
            )
        )

    out_ann_file = output_dir / "annotations.json"
    label_files = sorted(Path(args.input_dir).glob("*.json"))
    for image_id, path in enumerate(label_files):
        print("Generating dataset from:", path)

        label_file = utils.load_label_file(str(path))

        base = path.stem
        out_img_file = output_dir / "JPEGImages" / f"{base}.jpg"

        img = utils.img_data_to_arr(label_file.image_data)
        if img.ndim == 3 and img.shape[2] == 4:
            img = imgviz.rgba2rgb(img)
        imgviz.io.imsave(out_img_file, img)
        data["images"].append(
            dict(
                license=0,
                url=None,
                file_name=str(out_img_file.relative_to(output_dir)),
                height=img.shape[0],
                width=img.shape[1],
                date_captured=None,
                id=image_id,
            )
        )

        masks = {}  # for area
        segmentations = collections.defaultdict(list)  # for segmentation
        for shape in label_file.shapes:
            points: list[list[int | float]] = shape["points"]
            label = shape["label"]
            group_id = shape.get("group_id")
            shape_type = shape.get("shape_type", "polygon")
            mask = utils.shape_to_mask(img.shape[:2], points, shape_type)

            if group_id is None:
                group_id = uuid.uuid1()

            instance = (label, group_id)

            if instance in masks:
                masks[instance] = masks[instance] | mask
            else:
                masks[instance] = mask

            points_coco: list[int | float]
            if shape_type == "rectangle":
                (x1, y1), (x2, y2) = points
                x1, x2 = sorted([x1, x2])
                y1, y2 = sorted([y1, y2])
                points_coco = [x1, y1, x2, y1, x2, y2, x1, y2]
            elif shape_type == "circle":
                (cx, cy), (ex, ey) = points
                points_coco = _circle_to_polygon_segmentation(
                    center=(cx, cy), edge=(ex, ey)
                )
            else:
                points_coco = np.asarray(points).flatten().tolist()

            segmentations[instance].append(points_coco)
        segmentations = dict(segmentations)

        for instance, mask in masks.items():
            cls_name, group_id = instance
            if cls_name not in class_name_to_id:
                continue
            cls_id = class_name_to_id[cls_name]

            mask = np.asfortranarray(mask.astype(np.uint8))
            mask = pycocotools.mask.encode(mask)
            area = float(pycocotools.mask.area(mask))
            bbox = pycocotools.mask.toBbox(mask).flatten().tolist()

            data["annotations"].append(
                dict(
                    id=len(data["annotations"]),
                    image_id=image_id,
                    category_id=cls_id,
                    segmentation=segmentations[instance],
                    area=area,
                    bbox=bbox,
                    iscrowd=0,
                )
            )

        if not args.noviz:
            viz = img
            if masks:
                labels, captions, masks = zip(
                    *[
                        (class_name_to_id[cnm], cnm, msk)
                        for (cnm, gid), msk in masks.items()
                        if cnm in class_name_to_id
                    ]
                )
                viz = imgviz.instances2rgb(
                    image=img,
                    labels=labels,
                    masks=masks,
                    captions=captions,
                    font_size=15,
                    line_width=2,
                )
            out_viz_file = output_dir / "Visualization" / f"{base}.jpg"
            imgviz.io.imsave(out_viz_file, viz)

    with open(out_ann_file, "w") as f:
        json.dump(data, f)


if __name__ == "__main__":
    main()
