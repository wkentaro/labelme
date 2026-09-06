import argparse
from pathlib import Path

import numpy as np
import PIL.Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("label_png", type=Path)
    parser.add_argument("label_names", type=Path)
    args = parser.parse_args()

    lbl = np.asarray(PIL.Image.open(args.label_png))
    labels = np.unique(lbl)
    label_names = args.label_names.read_text(encoding="utf-8").splitlines()
    if len(labels) != len(label_names):
        parser.error("the number of names must match the number of label values")

    for label, label_name in zip(labels, label_names):
        print(f"{label}: {label_name}")


if __name__ == "__main__":
    main()
