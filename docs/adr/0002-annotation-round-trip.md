# Annotation owns the round-trip; the disk codec stays Qt-free

A single frozen `Annotation` type (evolved from `LabelData`) owns the in-memory
load/save round-trip and is used by the app on both boundaries, so the field set
has one owner instead of being re-encoded across `_load_shape_json_obj`,
`ShapeDict`, `Shape.__init__`, `_shapes_from_dicts`, and `_shape_to_dict`. The
on-disk codec (`read_label_file` / `write_label_file` in `_label_file.py`) stays
free of any PyQt5 import and continues to exchange plain-data `ShapeDict`, so the
persistence layer remains usable without a GUI.

## Considered options

- **Push the live `Shape` into the codec and delete `ShapeDict`** (rejected):
  `Shape` carries `QtCore.QPointF` points and render state, so making the codec
  hold it drags PyQt5 into `_label_file.py`. Four headless example scripts
  (`examples/instance_segmentation/labelme2voc.py`, `labelme2coco.py`,
  `examples/tutorial/export_json.py`, `draw_json.py`) and the Qt-free
  `tests/unit/_label_file_test.py` round-trip depend on that module staying
  GUI-free. `ShapeDict` is retained on purpose as the Qt-free wire format between
  the codec and `Annotation`.
- **Make the owner the mutable `LabelFile` lineage** (rejected): `LabelFile` is
  public (`labelme.LabelFile`), carries deprecated camelCase properties, and has
  an incoherent `save()` that ignores its own state. Reusing it would entangle
  this change with a public-API deprecation cycle. A frozen snapshot also fits
  the model where the Qt widgets remain the source of truth during editing.
  `LabelFile` is left untouched as a deprecated shim.
- **Make `Annotation` the live aggregate root** (deferred, not rejected): having
  `label_list`, `flag_list`, and the canvas read and mutate through `Annotation`
  would remove the existing `canvas.shapes` / `label_list` sync, but it needs a
  Qt model/view migration and reroutes roughly seven mutation entry points. The
  round-trip type defined here is the prerequisite for that move.

## Consequences

- Three shape representations coexist by design: the JSON object, the plain-data
  `ShapeDict`, and the live `Shape`. This is intentional layering, not
  duplication, because the field set now has a single owner.
- The `Shape` \<-> `ShapeDict` converters stay at the app boundary for now. A
  later step may move them onto `Annotation` as private implementation, but never
  into the Qt-free codec.
- A future architecture review should not re-suggest collapsing `ShapeDict` or
  pushing `Shape` into `_label_file.py`; doing so breaks the headless consumers
  above.

## Amendment (2026-06): `Shape` is now Qt-free

The rejection of "delete `ShapeDict`" above rested entirely on one premise:
`Shape` carried `QtCore.QPointF` points and Qt render state, so reusing it in the
codec would drag PyQt5 into `_label_file.py`. That premise no longer holds.
`Shape` has been refactored into a Qt-free `@dataclass` (`_shape.py`): `points` /
`point_labels` are numpy arrays, render state moved to `_widgets/_shape_render.py`
and `_widgets/canvas.py`, and the module imports no PyQt5. The in-progress drawing
shape is a separate QPointF `_DraftShape` in the canvas; committed shapes are the
Qt-free `Shape`.

Consequently the prohibition is lifted: collapsing `ShapeDict` into the Qt-free
`Shape` (so the codec exchanges one type) is now viable and no longer breaks the
headless consumers — they would import a numpy-only `Shape`. That collapse
(formerly "rejected") is now an unblocked but **deferred** follow-up; `ShapeDict`
is retained for now so this refactor stayed scoped to making `Shape` Qt-free.
Pushing `Shape` into `_label_file.py` remains inadvisable only for layering
reasons, not Qt ones.

## Amendment (2026-06): the `LabelFile` shim is removed

The second rejected option above kept the public `LabelFile` class "untouched as
a deprecated shim". It is now removed outright: nothing in the app or examples
consumed it once `examples/` became self-contained, so the deprecated camelCase
properties and the incoherent `save()` are gone. `read_label_file` /
`write_label_file` and the `LabelFileError` hierarchy remain the only persistence
entry points, which is the model that option already endorsed.
