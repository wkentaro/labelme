# labelme

The domain language of labelme, a desktop image-annotation tool. This glossary covers the user-facing data model — what an annotated Image consists of and how its parts relate.

## Language

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

## Flagged ambiguities

- **`LabelFile` / `LabelData` in code**: legacy identifiers for what the glossary calls an **Annotation File**. A rename to `AnnotationFile` is under consideration but not decided.

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
