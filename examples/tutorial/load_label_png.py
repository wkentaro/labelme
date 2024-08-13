#!/usr/bin/env python


import os.path as osp

import numpy as np
import PIL.Image

here = osp.dirname(osp.abspath(__file__))


def main():
    label_png = osp.join(here, "apc2016_obj3/label.png")
    print("Loading:", label_png)
    print()

    lbl = np.asarray(PIL.Image.open(label_png))
    labels = np.unique(lbl)

    label_names_txt = osp.join(here, "apc2016_obj3/label_names.txt")
    label_names = [name.strip() for name in open(label_names_txt)]
    print("# of labels:", len(labels))
    print("# of label_names:", len(label_names))
    if len(labels) != len(label_names):
        print("Number of unique labels and label_names must be same.")
        quit(1)
    print()

    print("label: label_name")
    for label, label_name in zip(labels, label_names):
        print(f"{label}: {label_name}")


if __name__ == "__main__":
    main()
