import json
import os.path as osp

import numpy as np
import PIL.Image

import labelme


here = osp.dirname(osp.abspath(__file__))
data_dir = osp.join(here, 'data')


def _get_img_and_data():
    json_file = osp.join(data_dir, 'apc2016_obj3.json')
    data = json.load(open(json_file))
    img_b64 = data['imageData']
    img = labelme.utils.img_b64_to_arr(img_b64)
    return img, data


def _get_img_and_lbl():
    img, data = _get_img_and_data()

    label_name_to_value = {'__background__': 0}
    for shape in data['shapes']:
        label_name = shape['label']
        label_value = len(label_name_to_value)
        label_name_to_value[label_name] = label_value

    n_labels = max(label_name_to_value.values()) + 1
    label_names = [None] * n_labels
    for label_name, label_value in label_name_to_value.items():
        label_names[label_value] = label_name

    lbl = labelme.utils.shapes_to_label(
        img.shape, data['shapes'], label_name_to_value)
    return img, lbl, label_names


# -----------------------------------------------------------------------------


def test_img_b64_to_arr():
    img, _ = _get_img_and_data()
    assert img.dtype == np.uint8
    assert img.shape == (907, 1210, 3)


def test_img_arr_to_b64():
    img_file = osp.join(data_dir, 'apc2016_obj3.jpg')
    img_arr = np.asarray(PIL.Image.open(img_file))
    img_b64 = labelme.utils.img_arr_to_b64(img_arr)
    img_arr2 = labelme.utils.img_b64_to_arr(img_b64)
    np.testing.assert_allclose(img_arr, img_arr2)


def test_shapes_to_label():
    img, data = _get_img_and_data()
    label_name_to_value = {}
    for shape in data['shapes']:
        label_name = shape['label']
        label_value = len(label_name_to_value)
        label_name_to_value[label_name] = label_value
    cls = labelme.utils.shapes_to_label(
        img.shape, data['shapes'], label_name_to_value)
    assert cls.shape == img.shape[:2]


def test_polygons_to_mask():
    img, data = _get_img_and_data()
    for shape in data['shapes']:
        polygons = shape['points']
        mask = labelme.utils.polygons_to_mask(img.shape[:2], polygons)
        assert mask.shape == img.shape[:2]


def test_label_colormap():
    N = 255
    colormap = labelme.utils.label_colormap(N=N)
    assert colormap.shape == (N, 3)


def test_label2rgb():
    img, lbl, label_names = _get_img_and_lbl()
    n_labels = len(label_names)

    viz = labelme.utils.label2rgb(lbl=lbl, n_labels=n_labels)
    assert lbl.shape == viz.shape[:2]
    assert viz.dtype == np.uint8

    viz = labelme.utils.label2rgb(lbl=lbl, img=img, n_labels=n_labels)
    assert img.shape[:2] == lbl.shape == viz.shape[:2]
    assert viz.dtype == np.uint8


def test_draw_label():
    img, lbl, label_names = _get_img_and_lbl()

    viz = labelme.utils.draw_label(lbl, img, label_names=label_names)
    assert viz.shape[:2] == img.shape[:2] == lbl.shape[:2]
    assert viz.dtype == np.uint8
