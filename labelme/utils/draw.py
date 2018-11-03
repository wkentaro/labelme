import io
import os.path as osp

import numpy as np
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont


def label_colormap(N=256):

    def bitget(byteval, idx):
        return ((byteval & (1 << idx)) != 0)

    cmap = np.zeros((N, 3))
    for i in range(0, N):
        id = i
        r, g, b = 0, 0, 0
        for j in range(0, 8):
            r = np.bitwise_or(r, (bitget(id, 0) << 7 - j))
            g = np.bitwise_or(g, (bitget(id, 1) << 7 - j))
            b = np.bitwise_or(b, (bitget(id, 2) << 7 - j))
            id = (id >> 3)
        cmap[i, 0] = r
        cmap[i, 1] = g
        cmap[i, 2] = b
    cmap = cmap.astype(np.float32) / 255
    return cmap


def _validate_colormap(colormap, n_labels):
    if colormap is None:
        colormap = label_colormap(n_labels)
    else:
        assert colormap.shape == (colormap.shape[0], 3), \
            'colormap must be sequence of RGB values'
        assert 0 <= colormap.min() and colormap.max() <= 1, \
            'colormap must ranges 0 to 1'
    return colormap


# similar function as skimage.color.label2rgb
def label2rgb(
    lbl, img=None, n_labels=None, alpha=0.5, thresh_suppress=0, colormap=None,
):
    if n_labels is None:
        n_labels = len(np.unique(lbl))

    colormap = _validate_colormap(colormap, n_labels)
    colormap = (colormap * 255).astype(np.uint8)

    lbl_viz = colormap[lbl]
    lbl_viz[lbl == -1] = (0, 0, 0)  # unlabeled

    if img is not None:
        img_gray = PIL.Image.fromarray(img).convert('LA')
        img_gray = np.asarray(img_gray.convert('RGB'))
        # img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        # img_gray = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2RGB)
        lbl_viz = alpha * lbl_viz + (1 - alpha) * img_gray
        lbl_viz = lbl_viz.astype(np.uint8)

    return lbl_viz


def draw_label(label, img=None, label_names=None, colormap=None, **kwargs):
    """Draw pixel-wise label with colorization and label names.

    label: ndarray, (H, W)
        Pixel-wise labels to colorize.
    img: ndarray, (H, W, 3), optional
        Image on which the colorized label will be drawn.
    label_names: iterable
        List of label names.
    """
    import matplotlib.pyplot as plt

    backend_org = plt.rcParams['backend']
    plt.switch_backend('agg')

    plt.subplots_adjust(left=0, right=1, top=1, bottom=0,
                        wspace=0, hspace=0)
    plt.margins(0, 0)
    plt.gca().xaxis.set_major_locator(plt.NullLocator())
    plt.gca().yaxis.set_major_locator(plt.NullLocator())

    if label_names is None:
        label_names = [str(l) for l in range(label.max() + 1)]

    colormap = _validate_colormap(colormap, len(label_names))

    label_viz = label2rgb(
        label, img, n_labels=len(label_names), colormap=colormap, **kwargs
    )
    plt.imshow(label_viz)
    plt.axis('off')

    plt_handlers = []
    plt_titles = []
    for label_value, label_name in enumerate(label_names):
        if label_value not in label:
            continue
        fc = colormap[label_value]
        p = plt.Rectangle((0, 0), 1, 1, fc=fc)
        plt_handlers.append(p)
        plt_titles.append('{value}: {name}'
                          .format(value=label_value, name=label_name))
    plt.legend(plt_handlers, plt_titles, loc='lower right', framealpha=.5)

    f = io.BytesIO()
    plt.savefig(f, bbox_inches='tight', pad_inches=0)
    plt.cla()
    plt.close()

    plt.switch_backend(backend_org)

    out_size = (label_viz.shape[1], label_viz.shape[0])
    out = PIL.Image.open(f).resize(out_size, PIL.Image.BILINEAR).convert('RGB')
    out = np.asarray(out)
    return out


def draw_instances(
    image=None,
    bboxes=None,
    labels=None,
    masks=None,
    captions=None,
):
    import matplotlib

    # TODO(wkentaro)
    assert image is not None
    assert bboxes is not None
    assert labels is not None
    assert masks is None
    assert captions is not None

    viz = PIL.Image.fromarray(image)
    draw = PIL.ImageDraw.ImageDraw(viz)

    font_path = osp.join(
        osp.dirname(matplotlib.__file__),
        'mpl-data/fonts/ttf/DejaVuSans.ttf'
    )
    font = PIL.ImageFont.truetype(font_path)

    colormap = label_colormap(255)
    for bbox, label, caption in zip(bboxes, labels, captions):
        color = colormap[label]
        color = tuple((color * 255).astype(np.uint8).tolist())

        xmin, ymin, xmax, ymax = bbox
        draw.rectangle((xmin, ymin, xmax, ymax), outline=color)
        draw.text((xmin, ymin), caption, font=font)

    return np.asarray(viz)
