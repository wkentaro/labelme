import json
import os.path as osp

import labelme.utils


def assert_labelfile_sanity(filename):
    assert osp.exists(filename)

    data = json.load(open(filename))

    assert 'imagePath' in data
    imageData = data.get('imageData', None)
    if imageData is None:
        assert osp.exists(data['imagePath'])
    img = labelme.utils.img_b64_to_arr(imageData)

    H, W = img.shape[:2]
    assert 'shapes' in data
    for shape in data['shapes']:
        assert 'label' in shape
        assert 'points' in shape
        for x, y in shape['points']:
            assert 0 <= x <= W
            assert 0 <= y <= H
