import os.path as osp

import numpy as np
import PIL.Image

from labelme.utils import image as image_module

from .util import data_dir
from .util import get_img_and_data


def test_img_b64_to_arr():
    img, _ = get_img_and_data()
    assert img.dtype == np.uint8
    assert img.shape == (907, 1210, 3)


def test_img_arr_to_b64():
    img_file = osp.join(data_dir, "annotated_with_data/apc2016_obj3.jpg")
    img_arr = np.asarray(PIL.Image.open(img_file))
    img_b64 = image_module.img_arr_to_b64(img_arr)
    img_arr2 = image_module.img_b64_to_arr(img_b64)
    np.testing.assert_allclose(img_arr, img_arr2)


def test_img_data_to_png_data():
    img_file = osp.join(data_dir, "annotated_with_data/apc2016_obj3.jpg")
    with open(img_file, "rb") as f:
        img_data = f.read()
    png_data = image_module.img_data_to_png_data(img_data)
    assert isinstance(png_data, bytes)
