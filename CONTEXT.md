# labelme

The domain language of labelme, a desktop image-annotation tool. This glossary covers the user-facing data model — what an annotated Image consists of and how its parts relate.

## Language

### Data model

**Annotation**:
The complete bundle of labelme data attached to one Image — its image-level Flags, its Shapes, and the per-Shape Flags carried by each Shape. Persisted as one JSON file on disk.
_Avoid_: using "annotation" for a single Shape.

**Shape**:
One drawn region on an Image with a class Label. Concrete kinds are distinguished by `shape_type` (polygon, rectangle, circle, line, point, linestrip, mask). A Shape is one constituent of an Annotation, never the whole.
_Avoid_: annotation (for a single region), region, marker, primitive.

**Flag**:
A boolean tag attached to the Image as a whole, used for image-level classification or cleaning (e.g. `cat`, `dog`, `blurry`). Lives at the top of the Annotation alongside Shapes.
_Avoid_: tag, attribute, image label.

**Shape Flag**:
A boolean attribute attached to one Shape (e.g. `occluded`, `truncated`). Same data shape as a Flag but a different concept — it qualifies a single Shape, not the Image.
_Avoid_: flag (unqualified), attribute, modifier.

**Label**:
The class string on a Shape (e.g. `"cat"`, `"car"`). One Shape has exactly one Label. Labels are not Annotations — they are a property of one Shape.
_Avoid_: class, category, tag, name; also avoid "label" to mean the Annotation File.

**Annotation File**:
The on-disk persisted form of one Annotation, stored as JSON. There is one Annotation File per Image. Identified in code as `LabelFile` / `LabelData` for historical reasons — that legacy name is not promoted as glossary vocabulary.
_Avoid_: label file, JSON file (when more precision is helpful), annotation json.

**Group**:
A set of Shapes sharing a common `group_id`, marking them as belonging together. The reason for grouping is application-defined — instance segmentation uses it for the visible parts of one occluded object, but the concept is general and not tied to any one use case.
_Avoid_: instance (it is only one application of grouping), cluster.

**AI Assist**:
Interactive, click-driven Shape proposal: the user places positive / negative points on the Image and a vision model (SAM, EfficientSAM) returns a proposed Shape. One user action produces one candidate Shape.
_Avoid_: AI annotation (too vague — covers AI Text Prompt too), auto-annotation, automation.

**AI Text Prompt**:
Bulk, text-driven Shape proposal: the user types a class name and an open-vocabulary detector (YOLO-world, SAM3) returns Shapes for every matching instance in the Image. One user action produces many candidate Shapes.
_Avoid_: AI annotation (too vague), text-to-annotation (verbose), auto-detect.

**Model Session**:
A loaded ML model that backs AI Assist or AI Text Prompt. One Model Session serves many proposals across the lifetime of the app. The legacy code directory `_automation/` hosts this layer.
_Avoid_: automation (legacy code-only term), backend, engine.

**Mask Shape**:
A Shape whose `shape_type` is `mask` — hybrid representation combining a rectangular bounding box (2 points) with a Mask (the raster pixels) that fills the bbox. The only `shape_type` that carries dense pixel data.
_Avoid_: raster shape, pixel polygon; do not say "mask" when you mean the whole Shape.

**Mask**:
The boolean pixel array inside a Mask Shape — one bit per pixel of the Mask Shape's bbox indicating whether the pixel belongs to the annotated region. Serialized as a base64-encoded PNG inside the Annotation File.
_Avoid_: bitmap, raster, segmentation map (when you mean just this Shape's pixels).

**Image**:
An input image file (PNG, JPEG, TIFF, etc.) that is the subject of an Annotation. Identified by its path on disk. The in-memory pixel array used while annotating is an implementation concern and not part of this term.
_Avoid_: photo, picture, file, frame.

**Label List**:
The predefined set of allowed Label strings configured for an annotation session (via the `--labels` CLI flag, a labels file, or the user config). The Label List is the *permitted vocabulary*; it is not the same as the Labels that actually appear on Shapes.
_Avoid_: labels (means actual labels in use), label vocabulary (verbose), classes.

### Configuration

**Settings**:
The user-adjustable annotation and behavior values (auto-save, drawing colors, shortcuts, AI model, and so on). Each Setting is a *value*, not a control: the value is the source of truth (persisted in the Config File) and may be surfaced by more than one **Setting Control** at once, all bound to it and kept in sync.
_Avoid_: preferences (only the historical menu label), config (that is the file, not the values), options.

**Setting Control**:
A UI element bound to a Setting that displays and edits its value: a checkable menu/toolbar action, an inline dock control, or a widget in the Settings dialog. Inline controls are reserved for Settings toggled frequently or meaningful only in context; the Settings dialog is the comprehensive home that exposes every Setting. Multiple Setting Controls for one Setting stay in sync through a single apply path.
_Avoid_: toggle (only one kind), widget, knob.

**Config File**:
The on-disk YAML where Settings are persisted as sparse Overrides on top of the Default Config. Defaults to `~/.labelmerc`, but can be relocated, e.g. a `labelmerc` file beside the executable in standalone builds, or any path passed to `--config`. The file is called "config"; the values it carries are Settings.
_Avoid_: settings file, rc file, labelmerc.

**Default Config**:
The baseline Settings shipped in `labelme/config/default_config.yaml`. Read-only, and the single source of both every default value and the set of allowed keys.
_Avoid_: defaults file, base config, schema.

**Override**:
A single Setting in the Config File whose value differs from the Default Config. The Config File holds only Overrides; resetting a Setting to its default removes its Override and keeps the file sparse.
_Avoid_: customization, change, diff.

**Window State**:
The window geometry and dock layout persisted via Qt's `QSettings` store (the `self._window_state` attribute in code), separate from Settings and never written to the Config File. Cleared by `--reset-config`.
_Avoid_: settings (those are the annotation/behavior values), config, layout config.

## Flagged ambiguities

- **`Annotation` / `LabelFile` in code**: the `Annotation` type names the in-memory **Annotation** (the whole bundle); it supersedes the former `LabelData`. `LabelFile` stays as the legacy identifier for the **Annotation File** (the on-disk form). The previously-mooted `LabelFile` → `AnnotationFile` rename remains deferred. The Qt-free codec functions (`read_label_file` / `write_label_file`) and their module (`_label_file.py`) keep the `label_file` name for now; renaming them to `read_annotation_file` / `write_annotation_file` (in an `_annotation.py` module) is the matching deferred cleanup, best done together with the `LabelFile` → `AnnotationFile` rename so the module is renamed once.
- **Concept vs file naming is an intentional split**: the user-facing values are **Settings**, but the file that persists them is the **Config File** (`~/.labelmerc`) and the CLI flag stays `--config`. The menu entry reads "Settings…" while keeping Qt's `PreferencesRole`. Do not "unify" the file/flag/role naming to "settings".

## Example dialogue

A new contributor (N) asks a maintainer (M) about a bug report.

> **N:** A user filed a bug saying their annotations get wiped when they reopen an image. What's actually being wiped?
>
> **M:** Probably the Annotation, not just one Shape. The Annotation includes the Image's Flags, every Shape on it, and the Shape Flags on each Shape. If the Annotation File didn't load, all of that is gone from view.
>
> **N:** Is the Annotation File on disk corrupted, or is the load failing?
>
> **M:** Check the file first. If it parses, the Annotation is fine; the UI just isn't picking it up. If it doesn't parse, the Annotation File itself is the problem.
>
> **N:** They also said their AI shapes disappear. They use AI Text Prompt — type "person", get a bunch of Shapes.
>
> **M:** Right. Those are still ordinary Shapes once the Model Session returns them; AI Text Prompt only produces them. After that they're stored in the Annotation File like any other Shape.
>
> **N:** They mentioned one Shape is a Mask Shape — does that change anything?
>
> **M:** Only the storage. A Mask Shape has a bbox plus an embedded Mask — the boolean pixel array, base64-encoded inside the Annotation File. If the file got truncated, the Mask is the most likely thing to be malformed.
>
> **N:** Last thing — they want Shapes from one occluded car to share a `group_id`. Is that an Instance?
>
> **M:** It's a Group. Instance segmentation is one application of grouping, but in our domain we just say Group. The Shapes share a `group_id` — that's all the data model knows about it.
