#!/usr/bin/env python

from __future__ import print_function

import argparse
import glob
import json
import os
import os.path as osp
import sys

try:
    import lxml.builder
    import lxml.etree
except ImportError:
    print('Please install lxml:\n\n    pip install lxml\n')
    sys.exit(1)
import numpy as np
import PIL.Image

import labelme


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('input_dir', help='input annotated directory')
    parser.add_argument('output_dir', help='output dataset directory')
    parser.add_argument('--labels', help='labels file', required=True)
    args = parser.parse_args()

    if osp.exists(args.output_dir):
        print('Output directory already exists:', args.output_dir)
        sys.exit(1)
    os.makedirs(args.output_dir)
    os.makedirs(osp.join(args.output_dir, 'JPEGImages'))
    os.makedirs(osp.join(args.output_dir, 'Annotations'))
    os.makedirs(osp.join(args.output_dir, 'AnnotationsVisualization'))
    print('Creating dataset:', args.output_dir)

    class_names = []
    class_name_to_id = {}
    for i, line in enumerate(open(args.labels).readlines()):
        class_id = i - 1  # starts with -1
        class_name = line.strip()
        class_name_to_id[class_name] = class_id
        if class_id == -1:
            assert class_name == '__ignore__'
            continue
        elif class_id == 0:
            assert class_name == '_background_'
        class_names.append(class_name)
    class_names = tuple(class_names)
    print('class_names:', class_names)
    out_class_names_file = osp.join(args.output_dir, 'class_names.txt')
    with open(out_class_names_file, 'w') as f:
        f.writelines('\n'.join(class_names))
    print('Saved class_names:', out_class_names_file)

    for label_file in glob.glob(osp.join(args.input_dir, '*.json')):
        print('Generating dataset from:', label_file)
        with open(label_file) as f:
            data = json.load(f)
        base = osp.splitext(osp.basename(label_file))[0]
        out_img_file = osp.join(
            args.output_dir, 'JPEGImages', base + '.jpg')
        out_xml_file = osp.join(
            args.output_dir, 'Annotations', base + '.xml')
        out_viz_file = osp.join(
            args.output_dir, 'AnnotationsVisualization', base + '.jpg')

        img_file = osp.join(osp.dirname(label_file), data['imagePath'])
        img = np.asarray(PIL.Image.open(img_file))
        PIL.Image.fromarray(img).save(out_img_file)

        maker = lxml.builder.ElementMaker()
        xml = maker.annotation(
            maker.folder(),
            maker.filename(base + '.jpg'),
            maker.database(),    # e.g., The VOC2007 Database
            maker.annotation(),  # e.g., Pascal VOC2007
            maker.image(),       # e.g., flickr
            maker.size(
                maker.height(str(img.shape[0])),
                maker.width(str(img.shape[1])),
                maker.depth(str(img.shape[2])),
            ),
            maker.segmented(),
        )

        bboxes = []
        labels = []
        for shape in data['shapes']:
            if shape['shape_type'] != 'rectangle':
                print('Skipping shape: label={label}, shape_type={shape_type}'
                      .format(**shape))
                continue

            class_name = shape['label']
            class_id = class_names.index(class_name)

            (xmin, ymin), (xmax, ymax) = shape['points']
            bboxes.append([xmin, ymin, xmax, ymax])
            labels.append(class_id)

            xml.append(
                maker.object(
                    maker.name(shape['label']),
                    maker.pose(),
                    maker.truncated(),
                    maker.difficult(),
                    maker.bndbox(
                        maker.xmin(str(xmin)),
                        maker.ymin(str(ymin)),
                        maker.xmax(str(xmax)),
                        maker.ymax(str(ymax)),
                    ),
                )
            )

        captions = [class_names[l] for l in labels]
        viz = labelme.utils.draw_instances(
            img, bboxes, labels, captions=captions
        )
        PIL.Image.fromarray(viz).save(out_viz_file)

        with open(out_xml_file, 'wb') as f:
            f.write(lxml.etree.tostring(xml, pretty_print=True))


if __name__ == '__main__':
    main()
