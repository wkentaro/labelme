import numpy as np
from PIL import Image, ImageDraw


def polygons_to_mask(polygons, img_shape):
    mask = np.zeros(img_shape, dtype=np.uint8)
    for polygon in polygons:
        polygon = polygon.reshape((-1, 1, 2))
        cv2.fillPoly(mask, polygon, 1)
    return mask


def shape_to_mask(
    img_shape,
    points,
    shape_type=None,
    line_width=10,
    point_size=5,
    point_type=None,
):
    mask = np.zeros(img_shape, dtype=np.uint8)
    xy = [list(points) for points in points]
    if shape_type == "rectangle":
        assert len(xy) == 2, "Shape of shape_type=rectangle must have 2 points"
        (x0, y0), (x1, y1) = xy
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        xy = [[x0, y0], [x1, y1]]
    elif shape_type == "circle":
        assert len(xy) == 2, "Shape of shape_type=circle must have 2 points"
        cx, cy = (xy[0] + xy[1]) / 2
        radius = max(abs(xy[0][0] - xy[1][0]), abs(xy[0][1] - xy[1][1])) / 2
        xy = [cx - radius, cy - radius, cx + radius, cy + radius]
    else:
        assert len(xy) > 2, "Polygon must have points more than 2"
    mask = Image.fromarray(mask)
    draw = ImageDraw.Draw(mask)
    if shape_type == "rectangle":
        draw.rectangle(xy, outline=1, fill=1)
    elif shape_type == "circle":
        draw.ellipse(xy, outline=1, fill=1)
    else:
        draw.polygon(xy, outline=1, fill=1)
    mask = np.array(mask, dtype=bool)
    return mask
