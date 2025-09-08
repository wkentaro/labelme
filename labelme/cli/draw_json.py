#!/usr/bin/env python

import argparse

import imgviz
import matplotlib.pyplot as plt

from labelme._label_file import LabelFile
from labelme.utils.image import img_data_to_arr
from labelme.utils.shape import shapes_to_label


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file")
    args = parser.parse_args()

    label_file = LabelFile(args.json_file)
    img = img_data_to_arr(label_file.imageData)

    label_name_to_value = {"_background_": 0}
    for shape in sorted(label_file.shapes, key=lambda x: x["label"]):
        label_name = shape["label"]
        if label_name in label_name_to_value:
            label_value = label_name_to_value[label_name]
        else:
            label_value = len(label_name_to_value)
            label_name_to_value[label_name] = label_value
    lbl, _ = shapes_to_label(img.shape, label_file.shapes, label_name_to_value)

    label_names = [None] * (max(label_name_to_value.values()) + 1)
    for name, value in label_name_to_value.items():
        label_names[value] = name  # type: ignore[call-overload]
    lbl_viz = imgviz.label2rgb(
        lbl,
        imgviz.asgray(img),
        label_names=label_names,
        font_size=30,
        loc="rb",
    )

    plt.subplot(121)
    plt.imshow(img)
    plt.subplot(122)
    plt.imshow(lbl_viz)
    plt.show()


if __name__ == "__main__":
    main()
