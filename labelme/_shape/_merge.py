from __future__ import annotations

import copy

import numpy as np
import numpy.typing as npt

from ._model import Shape


def can_merge_shapes(shapes: list[Shape], /) -> bool:
    return (
        len(shapes) > 1
        and all(s.shape_type == "mask" and s.mask is not None for s in shapes)
        and len({s.label for s in shapes}) == 1
    )


def _round_bbox_to_int(shape: Shape, /) -> tuple[int, int, int, int]:
    # Must match the AI Assist bbox rounding, so a merged bbox lands on the
    # same pixel grid as the Mask Shapes AI Assist produces.
    (xmin, ymin), (xmax, ymax) = shape.points
    return (
        int(round(float(xmin))),
        int(round(float(ymin))),
        int(round(float(xmax))),
        int(round(float(ymax))),
    )


def merge_masks(shapes: list[Shape], /) -> Shape:
    if not can_merge_shapes(shapes):
        raise ValueError("merge_masks needs 2+ Mask Shapes sharing one label")
    bboxes = [_round_bbox_to_int(s) for s in shapes]
    placed: list[tuple[int, int, npt.NDArray[np.bool_]]] = []
    for shape, (x0, y0, _, _) in zip(shapes, bboxes):
        assert shape.mask is not None
        placed.append((x0, y0, shape.mask))
    xmin = min(b[0] for b in bboxes)
    ymin = min(b[1] for b in bboxes)
    xmax = max(b[2] for b in bboxes)
    ymax = max(b[3] for b in bboxes)
    # The pixel canvas also covers each input's actual mask extent, since a
    # mask can drift larger than its bbox after vertex edits.
    height = max(ymax - ymin + 1, *(y0 - ymin + m.shape[0] for _, y0, m in placed))
    width = max(xmax - xmin + 1, *(x0 - xmin + m.shape[1] for x0, _, m in placed))
    # Exporters crop integer-bounded masks to their bbox, so it must cover every pixel.
    xmax, ymax = xmin + width - 1, ymin + height - 1
    mask = np.zeros((height, width), dtype=bool)
    for x0, y0, m in placed:
        h, w = m.shape
        mask[y0 - ymin : y0 - ymin + h, x0 - xmin : x0 - xmin + w] |= m
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
