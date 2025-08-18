#!/usr/bin/env python

import argparse
import collections
import datetime
import glob
import json
import os
import os.path as osp
import sys
import uuid
import multiprocessing
import imgviz
import numpy as np
import labelme

try:
    import pycocotools.mask
except ImportError:
    print("Please install pycocotools:\n\n    pip install pycocotools\n")
    sys.exit(1)


def process_label_file(args_tuple):
    filename, output_dir,out_ann_file, class_name_to_id, noviz, image_id = args_tuple
    print("Generating dataset from:", filename)
    label_file = labelme.LabelFile(filename=filename)

    base = osp.splitext(osp.basename(filename))[0]
    out_img_file = osp.join(output_dir, "JPEGImages", base + ".jpg")

    img = labelme.utils.img_data_to_arr(label_file.imageData)
    imgviz.io.imsave(out_img_file, img)
    image_data = dict(
        license=0,
        url=None,
        file_name=osp.relpath(out_img_file, osp.dirname(out_ann_file)),
        height=img.shape[0],
        width=img.shape[1],
        date_captured=None,
        id=image_id,
    )

    annotations = []
    masks = {}  # for area
    segmentations = collections.defaultdict(list)  # for segmentation
    for shape in label_file.shapes:
        points = shape["points"]
        label = shape["label"]
        group_id = shape.get("group_id")
        shape_type = shape.get("shape_type", "polygon")
        mask = labelme.utils.shape_to_mask(img.shape[:2], points, shape_type)

        if group_id is None:
            group_id = uuid.uuid1()

        instance = (label, group_id)

        if instance in masks:
            masks[instance] = masks[instance] | mask
        else:
            masks[instance] = mask

        if shape_type == "rectangle":
            (x1, y1), (x2, y2) = points
            x1, x2 = sorted([x1, x2])
            y1, y2 = sorted([y1, y2])
            points = [x1, y1, x2, y1, x2, y2, x1, y2]
        if shape_type == "circle":
            (x1, y1), (x2, y2) = points
            r = np.linalg.norm([x2 - x1, y2 - y1])
            # r(1-cos(a/2))<x, a=2*pi/N => N>pi/arccos(1-x/r)
            # x: tolerance of the gap between the arc and the line segment
            n_points_circle = max(int(np.pi / np.arccos(1 - 1 / r)), 12)
            i = np.arange(n_points_circle)
            x = x1 + r * np.sin(2 * np.pi / n_points_circle * i)
            y = y1 + r * np.cos(2 * np.pi / n_points_circle * i)
            points = np.stack((x, y), axis=1).flatten().tolist()
        else:
            points = np.asarray(points).flatten().tolist()
        segmentations[instance].append(points)
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

        annotation = dict(
            id="{}_{}".format(image_id, len(annotations)),
            image_id=image_id,
            category_id=cls_id,
            segmentation=segmentations[instance],
            area=area,
            bbox=bbox,
            iscrowd=0,
        )
        annotations.append(annotation)
    if not noviz:
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
        out_viz_file = osp.join(output_dir, "Visualization", base + ".jpg")
        imgviz.io.imsave(out_viz_file, viz)
    return image_data, annotations


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("input_dir", help="input annotated directory")
    parser.add_argument("output_dir", help="output dataset directory")
    parser.add_argument("--labels", help="labels file", required=True)
    parser.add_argument("--threads", help="number of threads", type=int, default=1)
    parser.add_argument("--noviz", help="no visualization", action="store_true")
    args = parser.parse_args()

    if osp.exists(args.output_dir):
        print("Output directory already exists:", args.output_dir)
        sys.exit(1)
    os.makedirs(args.output_dir)
    os.makedirs(osp.join(args.output_dir, "JPEGImages"))
    if not args.noviz:
        os.makedirs(osp.join(args.output_dir, "Visualization"))
    print("Creating dataset:", args.output_dir)
    now = datetime.datetime.now()
    data = dict(
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
        images=[
            # license, url, file_name, height, width, date_captured, id
        ],
        type="instances",
        annotations=[
            # segmentation, area, iscrowd, image_id, bbox, category_id, id
        ],
        categories=[
            # supercategory, id, name
        ],
    )

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
    
    out_ann_file = osp.join(args.output_dir, "annotations.json")
    label_files = glob.glob(osp.join(args.input_dir, "*.json"))
    mp_args = [
        (filename, args.output_dir, out_ann_file, class_name_to_id, args.noviz, image_id) for image_id, filename in enumerate(label_files)
    ]

    pool = multiprocessing.Pool(processes=args.threads)
    results = pool.map(process_label_file, mp_args)
    pool.close()
    pool.join()

    
    now = datetime.datetime.now()

    for image_data, annotations in results:
        data["images"].append(image_data)
        data["annotations"].extend(annotations)

    with open(out_ann_file, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Dataset created:", args.output_dir)


if __name__ == "__main__":
    main()
