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
from .qt import add_actions
from .qt import distance
from .qt import distance_to_line
from .qt import format_shortcut
from .qt import label_validator
from .qt import new_action
from .qt import new_button
from .qt import new_icon
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


_DEPRECATED_ALIASES = {
    "addActions": add_actions,
    "distancetoline": distance_to_line,
    "fmtShortcut": format_shortcut,
    "labelValidator": label_validator,
    "newAction": new_action,
    "newButton": new_button,
    "newIcon": new_icon,
}


def __getattr__(name: str) -> object:
    target = _DEPRECATED_ALIASES.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"labelme.utils.{name} is deprecated; use labelme.utils.{target.__name__}",
        DeprecationWarning,
        stacklevel=2,
    )
    return target
