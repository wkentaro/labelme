from .util import get_img_and_data

from labelme.utils import shape as shape_module


def test_shapes_to_label():
    img, data = get_img_and_data()
    label_name_to_value = {}
    for shape in data['shapes']:
        label_name = shape['label']
        label_value = len(label_name_to_value)
        label_name_to_value[label_name] = label_value
    cls = shape_module.shapes_to_label(
        img.shape, data['shapes'], label_name_to_value)
    assert cls.shape == img.shape[:2]


def test_shape_to_mask():
    img, data = get_img_and_data()
    for shape in data['shapes']:
        points = shape['points']
        mask = shape_module.shape_to_mask(img.shape[:2], points)
        assert mask.shape == img.shape[:2]
