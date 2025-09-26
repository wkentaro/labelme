#!/usr/bin/env python

import argparse
import json
import os
import os.path as osp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", help="LabelMe JSON file")
    parser.add_argument("-o", "--output", help="Output directory")
    args = parser.parse_args()

    json_file = args.json_file
    
    if args.output is None:
        output_dir = osp.splitext(osp.basename(json_file))[0] + "_yolo"
        output_dir = osp.join(osp.dirname(json_file), output_dir)
    else:
        output_dir = args.output
    
    os.makedirs(output_dir, exist_ok=True)

    # Read JSON file
    with open(json_file, encoding='utf-8') as f:
        data = json.load(f)

    # Get image dimensions
    image_height = data.get('imageHeight', 0)
    image_width = data.get('imageWidth', 0)
    
    if image_height == 0 or image_width == 0:
        print("Error: Invalid image dimensions")
        return

    # Convert annotations
    yolo_annotations = []
    class_names = set()

    for shape in data.get('shapes', []):
        label = shape.get('label', '')
        shape_type = shape.get('shape_type', '')
        points = shape.get('points', [])

        if shape_type == 'rectangle' and len(points) == 2:
            # Convert rectangle to YOLO format
            x1, y1 = points[0]
            x2, y2 = points[1]

            center_x = (x1 + x2) / 2.0 / image_width
            center_y = (y1 + y2) / 2.0 / image_height
            width = abs(x2 - x1) / image_width
            height = abs(y2 - y1) / image_height

            class_names.add(label)
            class_id = sorted(class_names).index(label)

            yolo_annotations.append(
                f"{class_id} {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}"
            )

        elif shape_type == 'polygon' and len(points) >= 3:
            # Convert polygon to YOLO segmentation format
            normalized_points = []
            for x, y in points:
                normalized_points.extend([x / image_width, y / image_height])

            class_names.add(label)
            class_id = sorted(class_names).index(label)

            points_str = ' '.join([f"{p:.6f}" for p in normalized_points])
            yolo_annotations.append(f"{class_id} {points_str}")

    # Write output files
    base_name = osp.splitext(osp.basename(json_file))[0]

    # Write YOLO annotation file
    txt_path = osp.join(output_dir, f"{base_name}.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        for annotation in yolo_annotations:
            f.write(annotation + '\n')

    # Write classes file
    classes_path = osp.join(output_dir, "classes.txt")
    with open(classes_path, 'w', encoding='utf-8') as f:
        for class_name in sorted(class_names):
            f.write(class_name + '\n')

    print(f"Exported {len(yolo_annotations)} annotations to: {output_dir}")


if __name__ == "__main__":
    main()