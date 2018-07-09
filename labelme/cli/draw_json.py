#!/usr/bin/env python

import argparse
import base64
import json
import os
import sys

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

    lbl, label_name_to_value = utils.shapes_to_label(img.shape, data['shapes'])

    lbl = utils.shapes_to_label(
        img.shape, shapes=data['shapes'],
        label_name_to_value=label_name_to_value,
    )

    label_names = [None] * (max(label_name_to_value.values()) + 1)
    for name, value in label_name_to_value.items():
        label_names[value] = name
    lbl_viz = utils.draw_label(lbl, img, label_names)

    plt.subplot(121)
    plt.imshow(img)
    plt.subplot(122)
    plt.imshow(lbl_viz)
    plt.show()


if __name__ == '__main__':
    main()
