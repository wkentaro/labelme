#!/usr/bin/env python

import argparse
import json
import os
import os.path as osp
import warnings

import numpy as np
import PIL.Image
import yaml

from labelme import utils


def main():
    warnings.warn("This script is aimed to demonstrate how to convert the\n"
                "JSON file to a single image dataset, and not to handle\n"
                "multiple JSON files to generate a real-use dataset.")

    parser = argparse.ArgumentParser()
    parser.add_argument('json_file')
    parser.add_argument('-o', '--out', default=None)
    args = parser.parse_args()

    json_file = args.json_file

    if args.out is None:
        out_dir = osp.basename(json_file).replace('.', '_')
        out_dir = osp.join(osp.dirname(json_file), out_dir)
    else:
        out_dir = args.out
    if not osp.exists(out_dir):
        os.mkdir(out_dir)

    data = json.load(open(json_file))

    img = utils.img_b64_to_array(data['imageData'])
    lbl, lbl_names = utils.labelme_shapes_to_label(img.shape, data['shapes'])

    captions = ['%d: %s' % (l, name) for l, name in enumerate(lbl_names)]
    lbl_viz = utils.draw_label(lbl, img, captions)

    PIL.Image.fromarray(img).save(osp.join(out_dir, 'img.png'))
    PIL.Image.fromarray(lbl).save(osp.join(out_dir, 'label.png'))
    PIL.Image.fromarray(lbl_viz).save(osp.join(out_dir, 'label_viz.png'))

    with open(osp.join(out_dir, 'label_names.txt'), 'w') as f:
        for lbl_name in lbl_names:
            f.write(lbl_name + '\n')

    warnings.warn('info.yaml is being replaced by label_names.txt')
    info = dict(label_names=lbl_names)
    with open(osp.join(out_dir, 'info.yaml'), 'w') as f:
        yaml.safe_dump(info, f, default_flow_style=False)

    print('Saved to: %s' % out_dir)


if __name__ == '__main__':
    main()
