import json
import os.path as osp

from labelme.utils.image import img_b64_to_arr

here = osp.dirname(osp.abspath(__file__))
data_dir = osp.join(here, "../data")


def get_img_and_data():
    json_file = osp.join(data_dir, "annotated_with_data/apc2016_obj3.json")
    with open(json_file) as f:
        data = json.load(f)
    img_b64 = data["imageData"]
    img = img_b64_to_arr(img_b64)
    return img, data
