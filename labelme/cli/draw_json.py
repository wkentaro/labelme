#!/usr/bin/env python

import argparse
import json
import os
import sys
import base64
import matplotlib.pyplot as plt

from labelme import utils


PY2 = sys.version_info[0] == 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('json_file')
    args = parser.parse_args()

    json_file = args.json_file

    data = json.load(open(json_file))

    if data['imageData']:
        imageData = data['imageData']
    else:
        imagePath = os.path.join(os.path.dirname(json_file), data['imagePath'])
        with open(imagePath, 'rb') as f:
            imageData = f.read()
            imageData = base64.b64encode(imageData).decode('utf-8')

    img = utils.img_b64_to_arr(imageData)

    label_name_to_value = {'_background_': 0}
    for shape in data['shapes']:
        label_name = shape['label']
        if label_name in label_name_to_value:
            label_value = label_name_to_value[label_name]
        else:
            label_value = len(label_name_to_value)
            label_name_to_value[label_name] = label_value

    lbl = utils.shapes_to_label(
        img.shape, data['shapes'], label_name_to_value)

    captions = ['{}: {}'.format(lv, ln)
                for ln, lv in label_name_to_value.items()]
    lbl_viz = utils.draw_label(lbl, img, captions)

    plt.subplot(121)
    plt.imshow(img)
    plt.subplot(122)
    plt.imshow(lbl_viz)
    plt.show()


if __name__ == '__main__':
    main()
