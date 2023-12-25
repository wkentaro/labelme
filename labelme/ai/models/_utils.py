import numpy as np
import skimage
import PIL.Image
import imgviz


def _get_contour_length(contour):
    contour_start = contour
    contour_end = np.r_[contour[1:], contour[0:1]]
    return np.linalg.norm(contour_end - contour_start, axis=1).sum()


def compute_polygon_from_mask(mask):
    contours = skimage.measure.find_contours(np.pad(mask, pad_width=1))
    contour = max(contours, key=_get_contour_length)
    POLYGON_APPROX_TOLERANCE = 0.004
    polygon = skimage.measure.approximate_polygon(
        coords=contour,
        tolerance=np.ptp(contour, axis=0).max() * POLYGON_APPROX_TOLERANCE,
    )
    polygon = np.clip(polygon, (0, 0), (mask.shape[0] - 1, mask.shape[1] - 1))
    polygon = polygon[:-1]  # drop last point that is duplicate of first point

    if 0:
        image_pil = PIL.Image.fromarray(
            imgviz.gray2rgb(imgviz.bool2ubyte(mask))
        )
        imgviz.draw.line_(image_pil, yx=polygon, fill=(0, 255, 0))
        for point in polygon:
            imgviz.draw.circle_(
                image_pil, center=point, diameter=10, fill=(0, 255, 0)
            )
        imgviz.io.imsave("contour.jpg", np.asarray(image_pil))

    return polygon[:, ::-1]  # yx -> xy
