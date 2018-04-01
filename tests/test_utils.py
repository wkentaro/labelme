import json
import os.path as osp

import numpy as np
import PIL.Image

import labelme


here = osp.dirname(osp.abspath(__file__))
data_dir = osp.join(here, 'data')


def test_img_b64_to_arr():
    json_file = osp.join(data_dir, 'apc2016_obj3.json')
    data = json.load(open(json_file))
    img_b64 = data['imageData']
    img = labelme.utils.img_b64_to_arr(img_b64)
    assert img.dtype == np.uint8
    assert img.shape == (907, 1210, 3)


def test_img_arr_to_b64():
    img_file = osp.join(data_dir, 'apc2016_obj3.jpg')
    img_arr = np.asarray(PIL.Image.open(img_file))
    img_b64 = labelme.utils.img_arr_to_b64(img_arr)
    img_arr2 = labelme.utils.img_b64_to_arr(img_b64)
    np.testing.assert_allclose(img_arr, img_arr2)
