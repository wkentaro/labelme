import numpy as np

from labelme.utils import draw as draw_module
from labelme.utils import shape as shape_module

from .util import get_img_and_lbl


# -----------------------------------------------------------------------------


def test_label_colormap():
    N = 255
    colormap = draw_module.label_colormap(N=N)
    assert colormap.shape == (N, 3)


def test_label2rgb():
    img, lbl, label_names = get_img_and_lbl()
    n_labels = len(label_names)

    viz = draw_module.label2rgb(lbl=lbl, n_labels=n_labels)
    assert lbl.shape == viz.shape[:2]
    assert viz.dtype == np.uint8

    viz = draw_module.label2rgb(lbl=lbl, img=img, n_labels=n_labels)
    assert img.shape[:2] == lbl.shape == viz.shape[:2]
    assert viz.dtype == np.uint8


def test_draw_label():
    img, lbl, label_names = get_img_and_lbl()

    viz = draw_module.draw_label(lbl, img, label_names=label_names)
    assert viz.shape[:2] == img.shape[:2] == lbl.shape[:2]
    assert viz.dtype == np.uint8


def test_draw_instances():
    img, lbl, label_names = get_img_and_lbl()
    labels_and_masks = {l: lbl == l for l in np.unique(lbl) if l != 0}
    labels, masks = zip(*labels_and_masks.items())
    masks = np.asarray(masks)
    bboxes = shape_module.masks_to_bboxes(masks)
    captions = [label_names[l] for l in labels]
    viz = draw_module.draw_instances(img, bboxes, labels, captions=captions)
    assert viz.shape[:2] == img.shape[:2]
    assert viz.dtype == np.uint8
