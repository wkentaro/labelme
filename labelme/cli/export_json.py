import argparse
import os
import os.path as osp

import imgviz
import numpy as np
import numpy.typing as npt
import PIL.Image
from loguru import logger

from labelme import utils
from labelme._label_file import LabelFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args()

    json_file = args.json_file

    if args.out is None:
        out_dir = osp.splitext(osp.basename(json_file))[0]
        out_dir = osp.join(osp.dirname(json_file), out_dir)
    else:
        out_dir = args.out
    if not osp.exists(out_dir):
        os.mkdir(out_dir)

    label_file: LabelFile = LabelFile(filename=json_file)

    image: npt.NDArray[np.uint8] = utils.img_data_to_arr(label_file.imageData)

    label_name_to_value = {"_background_": 0}
    for shape in sorted(label_file.shapes, key=lambda x: x["label"]):
        label_name = shape["label"]
        if label_name in label_name_to_value:
            label_value = label_name_to_value[label_name]
        else:
            label_value = len(label_name_to_value)
            label_name_to_value[label_name] = label_value
    lbl, _ = utils.shapes_to_label(image.shape, label_file.shapes, label_name_to_value)

    label_names = [None] * (max(label_name_to_value.values()) + 1)
    for name, value in label_name_to_value.items():
        label_names[value] = name  # type: ignore[call-overload]

    lbl_viz = imgviz.label2rgb(
        lbl, imgviz.asgray(image), label_names=label_names, loc="rb"
    )

    PIL.Image.fromarray(image).save(osp.join(out_dir, "img.png"))
    utils.lblsave(osp.join(out_dir, "label.png"), lbl)
    PIL.Image.fromarray(lbl_viz).save(osp.join(out_dir, "label_viz.png"))

    with open(osp.join(out_dir, "label_names.txt"), "w") as f:
        for lbl_name in label_names:
            f.write(f"{lbl_name}\n")

    logger.info(f"Saved to: {out_dir}")


if __name__ == "__main__":
    main()
