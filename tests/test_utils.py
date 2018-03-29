import json
import os.path as osp

import numpy as np

from labelme import utils


here = osp.dirname(osp.abspath(__file__))


def test_img_b64_to_array():
    json_file = osp.join(here, '../examples/single_image/apc2016_obj3.json')
    data = json.load(open(json_file))
    img_b64 = data['imageData']
    img = utils.img_b64_to_array(img_b64)
    assert img.dtype == np.uint8
    assert img.shape == (907, 1210, 3)
