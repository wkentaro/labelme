from __future__ import annotations

import copy
from typing import Literal

import numpy as np

from ._hit_testing import mask_shape_box
from ._model import Shape

MergeBlocker = Literal["too_few", "not_masks", "locked", "mixed_labels"]


def merge_blocker(*, shapes: list[Shape]) -> MergeBlocker | None:
    # Ordered by what the user fixes first: a locked polygon reports
    # "not_masks", since unlocking it would still not make it mergeable.
    if len(shapes) <= 1:
        return "too_few"
    if any(s.shape_type != "mask" or s.mask is None for s in shapes):
        return "not_masks"
    if any(s.locked for s in shapes):
        return "locked"
    if len({s.label for s in shapes}) > 1:
        return "mixed_labels"
    return None


def can_merge_shapes(*, shapes: list[Shape]) -> bool:
    return merge_blocker(shapes=shapes) is None


def merge_masks(*, shapes: list[Shape]) -> Shape:
    if not can_merge_shapes(shapes=shapes):
        raise ValueError("merge_masks needs 2+ Mask Shapes sharing one label")
    boxes = [mask_shape_box(shape=s) for s in shapes]
    x0s, y0s, x1s, y1s = zip(*boxes, strict=True)
    xmin, ymin, xmax, ymax = min(x0s), min(y0s), max(x1s), max(y1s)
    mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=bool)
    for shape, (x0, y0, x1, y1) in zip(shapes, boxes, strict=True):
        assert shape.mask is not None
        mask[y0 - ymin : y1 - ymin + 1, x0 - xmin : x1 - xmin + 1] |= shape.mask
    first = shapes[0]
    return Shape(
        label=first.label,
        group_id=first.group_id,
        shape_type="mask",
        flags=copy.deepcopy(first.flags),
        description=first.description,
        mask=mask,
        points=np.array([[xmin, ymin], [xmax, ymax]], dtype=np.float64),
        other_data=copy.deepcopy(first.other_data),
    )
