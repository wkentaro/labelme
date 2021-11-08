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

import imgviz
import numpy as np
from sklearn.model_selection import train_test_split
import regex
import copy

import labelme

try:
    import pycocotools.mask
except ImportError:
    print("Please install pycocotools:\n\n    pip install pycocotools\n")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--input_dir", nargs='*', help="input annotated directory")
    parser.add_argument("--output_dir", help="output dataset directory")
    parser.add_argument("--labels", help="labels file", required=True)
    parser.add_argument("--noviz", help="no visualization", action="store_true")
    parser.add_argument('--split', type=float, nargs='?', default=0.9, help="Train set size; a number in (0, 1)")
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
        licenses=[dict(url=None, id=0, name=None,)],
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
            dict(supercategory=None, id=class_id, name=class_name,)
        )

    out_ann_file_all = osp.join(args.output_dir, "_coco.json")
    out_ann_file_train = osp.join(args.output_dir, "_train.json")
    out_ann_file_test = osp.join(args.output_dir, "_test.json")
    
    print("working directory is:", os.getcwd())
    
    label_files_per_dir = [] # label_files is a list of lists
    if args.input_dir is None:
        args.input_dir = [x[0] for x in os.walk(os.getcwd())]
        args.input_dir.sort(key=lambda f: int(regex.sub('\D', '', f)))
            
        print("input dir(s) are:", args.input_dir)
    
    if isinstance(args.input_dir, list):
        # multiple dirs were given:
        for dir in args.input_dir:
            label_files_per_dir.append(glob.glob(osp.join(dir, "*.json")))
    else:
        label_files_per_dir = [glob.glob(osp.join(args.input_dir, "*.json"))]
    
    data_train = copy.deepcopy(data)
    data_test = copy.deepcopy(data)
    
    image_id = 0
    for label_files in label_files_per_dir:
        
        # train, test split
        if len(label_files) > 0:
            train, test = train_test_split(label_files, train_size=args.split)
            
            for set_name, split_set in [("train", train), ("test", test)]:
                print("generating set:", set_name)
                for filename in split_set:
                    print("Generating dataset from:", filename)

                    label_file = labelme.LabelFile(filename=filename)

                    base = osp.splitext(osp.basename(filename))[0]
                    out_img_file = osp.join(args.output_dir, "JPEGImages", base + ".jpg")

                    img = labelme.utils.img_data_to_arr(label_file.imageData)
                    imgviz.io.imsave(out_img_file, img)
                    image_data = dict(
                            license=0,
                            url=None,
                            file_name=osp.relpath(out_img_file, osp.dirname(out_ann_file_all)),
                            height=img.shape[0],
                            width=img.shape[1],
                            date_captured=None,
                            id=image_id,
                        )

                    masks = {}  # for area
                    segmentations = collections.defaultdict(list)  # for segmentation
                    for shape in label_file.shapes:
                        points = shape["points"]
                        label = shape["label"]
                        group_id = shape.get("group_id")
                        shape_type = shape.get("shape_type", "polygon")
                        mask = labelme.utils.shape_to_mask(
                            img.shape[:2], points, shape_type
                        )

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
                        else:
                            points = np.asarray(points).flatten().tolist()

                        segmentations[instance].append(points)
                    segmentations = dict(segmentations)

                    if len(masks.keys()) > 0:
                        # image contains annotations, so add it.
                        data["images"].append(image_data)
                        if set_name == "train":
                            data_train["images"].append(image_data)
                            
                        if set_name == "test":
                            data_test["images"].append(image_data)

                    for instance, mask in masks.items():
                        cls_name, group_id = instance
                        if cls_name not in class_name_to_id:
                            continue
                        cls_id = class_name_to_id[cls_name]

                        mask = np.asfortranarray(mask.astype(np.uint8))
                        mask = pycocotools.mask.encode(mask)
                        area = float(pycocotools.mask.area(mask))
                        bbox = pycocotools.mask.toBbox(mask).flatten().tolist()

                        annotation_data = dict(
                                id=len(data["annotations"]),
                                image_id=image_id,
                                category_id=cls_id,
                                segmentation=segmentations[instance],
                                area=area,
                                bbox=bbox,
                                iscrowd=0,
                            )
                        data["annotations"].append(annotation_data)
                        if set_name == "train":
                            data_train["annotations"].append(annotation_data)
                            
                        if set_name == "test":
                            data_test["annotations"].append(annotation_data)

                    if not args.noviz:
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
                        out_viz_file = osp.join(
                            args.output_dir, "Visualization", base + ".jpg"
                        )
                        imgviz.io.imsave(out_viz_file, viz)
                        
                    # increment image counter
                    image_id += 1

    with open(out_ann_file_all, "w") as f:
        json.dump(data, f)
        
    with open(out_ann_file_train, "w") as f:
        json.dump(data_train, f)
        
    with open(out_ann_file_test, "w") as f:
        json.dump(data_test, f)


if __name__ == "__main__":
    main()
