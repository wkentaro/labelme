import json
import os.path as osp

from labelme.utils.image import img_b64_to_arr
from labelme.utils.shape import shapes_to_label

here = osp.dirname(osp.abspath(__file__))
data_dir = osp.join(here, "../data")


def get_img_and_data():
    json_file = osp.join(data_dir, "annotated_with_data/apc2016_obj3.json")
    with open(json_file) as f:
        data = json.load(f)
    img_b64 = data["imageData"]
    img = img_b64_to_arr(img_b64)
    return img, data


def get_img_and_lbl():
    img, data = get_img_and_data()

    label_name_to_value = {"__background__": 0}
    for shape in data["shapes"]:
        label_name = shape["label"]
        label_value = len(label_name_to_value)
        label_name_to_value[label_name] = label_value

    n_labels = max(label_name_to_value.values()) + 1
    label_names = [None] * n_labels
    for label_name, label_value in label_name_to_value.items():
        label_names[label_value] = label_name

    lbl, _ = shapes_to_label(img.shape, data["shapes"], label_name_to_value)
    return img, lbl, label_names
