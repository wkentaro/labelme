import base64
import cStringIO as StringIO

import matplotlib.pyplot as plt
import numpy as np
import PIL.Image
import PIL.ImageDraw
import scipy.misc
import skimage.color


def labelcolormap(N=256):

    def bitget(byteval, idx):
        return ((byteval & (1 << idx)) != 0)

    cmap = np.zeros((N, 3))
    for i in xrange(0, N):
        id = i
        r, g, b = 0, 0, 0
        for j in xrange(0, 8):
            r = np.bitwise_or(r, (bitget(id, 0) << 7-j))
            g = np.bitwise_or(g, (bitget(id, 1) << 7-j))
            b = np.bitwise_or(b, (bitget(id, 2) << 7-j))
            id = (id >> 3)
        cmap[i, 0] = r
        cmap[i, 1] = g
        cmap[i, 2] = b
    cmap = cmap.astype(np.float32) / 255
    return cmap


def img_b64_to_array(img_b64):
    f = StringIO.StringIO()
    f.write(base64.b64decode(img_b64))
    img_arr = np.array(PIL.Image.open(f))
    return img_arr


def polygons_to_mask(img_shape, polygons):
    mask = np.zeros(img_shape[:2], dtype=np.uint8)
    mask = PIL.Image.fromarray(mask)
    xy = map(tuple, polygons)
    PIL.ImageDraw.Draw(mask).polygon(xy=xy, outline=1, fill=1)
    mask = np.array(mask, dtype=bool)
    return mask


def draw_label(label, img, label_names, colormap=None):
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0,
                        wspace=0, hspace=0)
    plt.margins(0, 0)
    plt.gca().xaxis.set_major_locator(plt.NullLocator())
    plt.gca().yaxis.set_major_locator(plt.NullLocator())

    if colormap is None:
        colormap = labelcolormap(len(label_names))

    label_viz = skimage.color.label2rgb(
        label, img, colors=colormap[1:], bg_label=0, bg_color=colormap[0])
    plt.imshow(label_viz)
    plt.axis('off')

    plt_handlers = []
    plt_titles = []
    for label_value, label_name in enumerate(label_names):
        fc = colormap[label_value]
        p = plt.Rectangle((0, 0), 1, 1, fc=fc)
        plt_handlers.append(p)
        plt_titles.append(label_name)
    plt.legend(plt_handlers, plt_titles, loc='lower right', framealpha=.5)

    f = StringIO.StringIO()
    plt.savefig(f, bbox_inches='tight', pad_inches=0)
    plt.cla()
    plt.close()

    out = np.array(PIL.Image.open(f))[:, :, :3]
    out = scipy.misc.imresize(out, img.shape[:2])
    return out


def labelme_shapes_to_label(img_shape, shapes):
    label_name_to_val = {'background': 0}
    lbl = np.zeros(img_shape[:2], dtype=np.int32)
    for shape in sorted(shapes, key=lambda x: x['label']):
        polygons = shape['points']
        label_name = shape['label']
        if label_name in label_name_to_val:
            label_value = label_name_to_val[label_name]
        else:
            label_value = len(label_name_to_val)
            label_name_to_val[label_name] = label_value
        mask = polygons_to_mask(img_shape[:2], polygons)
        lbl[mask] = label_value

    lbl_names = [None] * (max(label_name_to_val.values()) + 1)
    for label_name, label_value in label_name_to_val.items():
        lbl_names[label_value] = label_name

    return lbl, lbl_names
