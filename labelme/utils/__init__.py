import warnings

import imgviz.io
import numpy

from .image import apply_exif_orientation
from .image import img_arr_to_b64
from .image import img_arr_to_data
from .image import img_b64_to_arr
from .image import img_data_to_arr
from .image import img_data_to_pil
from .image import img_data_to_png_data
from .image import img_pil_to_data
from .image import img_qt_to_arr
from .qt import addActions
from .qt import distance
from .qt import distancetoline
from .qt import fmtShortcut
from .qt import labelValidator
from .qt import newAction
from .qt import newButton
from .qt import newIcon
from .shape import masks_to_bboxes
from .shape import shape_to_mask
from .shape import shapes_to_label


def lblsave(filename: str, lbl: numpy.ndarray) -> None:
    warnings.warn(
        "labelme.utils.lblsave is deprecated; use imgviz.io.lblsave",
        DeprecationWarning,
        stacklevel=2,
    )
    imgviz.io.lblsave(filename, lbl)
