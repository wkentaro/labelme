#!/usr/bin/env python

import argparse
from pathlib import Path
from typing import Final

import imgviz
import matplotlib.pyplot as plt
import numpy as np
from loguru import logger


def main() -> None:
    # json_to_dataset stores the ignore label as 255 in the 8-bit label PNG.
    UNLABELED_PNG_VALUE: Final = 255

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("label_png", help="label PNG file")
    parser.add_argument(
        "--labels",
        help="labels list (comma separated text or file)",
        default=None,
    )
    parser.add_argument("--image", help="image file", default=None)
    args = parser.parse_args()

    if args.labels is None:
        label_names = None
    elif Path(args.labels).exists():
        with open(args.labels) as f:
            label_names = [label.strip() for label in f]
    else:
        label_names = args.labels.split(",")

    if args.image is None:
        image = None
    else:
        image = imgviz.io.imread(args.image)

    label = imgviz.io.imread(args.label_png)
    label = label.astype(np.int32)
    label[label == UNLABELED_PNG_VALUE] = -1

    unique_label_values = np.unique(label)

    logger.info(f"Label image shape: {label.shape}")
    logger.info(f"Label values: {unique_label_values.tolist()}")
    if label_names is not None:
        logger.info(
            "Label names: {}".format(
                [
                    f"{label_value}:{label_names[label_value]}"
                    for label_value in unique_label_values
                ]
            )
        )

    if args.image:
        num_cols = 2
    else:
        num_cols = 1

    plt.figure(figsize=(num_cols * 6, 5))

    plt.subplot(1, num_cols, 1)
    plt.title(args.label_png)
    label_viz = imgviz.label2rgb(
        label=label, label_names=label_names, font_size=label.shape[1] // 30
    )
    plt.imshow(label_viz)

    if image is not None:
        plt.subplot(1, num_cols, 2)
        label_viz_with_overlay = imgviz.label2rgb(
            label=label,
            image=image,
            label_names=label_names,
            font_size=label.shape[1] // 30,
        )
        plt.title(f"{args.label_png}\n{args.image}")
        plt.imshow(label_viz_with_overlay)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
