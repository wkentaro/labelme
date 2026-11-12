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
A boolean attribute attached to one Shape (e.g. `occluded`, `truncated`). Same data shape as a Flag but a different concept — it qualifies a single Shape, not the Image. Label-matching rules offer defaults; changing the rules or the Label does not erase Shape Flags already carried by a Shape.
_Avoid_: flag (unqualified), attribute, modifier.

**Label**:
The class string on a Shape (e.g. `"cat"`, `"car"`). One Shape has exactly one Label. Labels are not Annotations — they are a property of one Shape.
_Avoid_: class, category, tag, name; also avoid "label" to mean the Annotation File.

**Annotation File**:
The on-disk persisted form of one Annotation, stored as JSON. There is one Annotation File per Image. The code reads and writes it with `read_label_file` / `write_label_file` in `labelme/_label_file.py`; the `label_file` name is historical and is not promoted as glossary vocabulary.
_Avoid_: label file, JSON file (when more precision is helpful), annotation json.

**Annotation Folder**:
The folder where Labelme reads and writes Annotation Files instead of next to each Image. Optional and unset by default, so each Annotation File sits next to its Image. When it is set, Labelme does not fall back to an Annotation File next to the Image. Set it with `--output` or Change Annotation Folder…. Labelme remembers it per opened folder in the Window State and restores it when that folder, or an Image in it, is opened again; `--output` replaces the remembered folder for the folder it is given with. Choosing one needs an opened folder, and an Annotation File opened directly leaves the opened folder's Annotation Folder behind. A remembered folder that no longer exists is skipped with a status-bar notice and kept for when it returns. Save As can still write the current Image's Annotation File elsewhere.
_Avoid_: output dir, save dir, label folder, annotations dir.

**Group**:
A set of Shapes sharing a common `group_id`, marking them as belonging together. The reason for grouping is application-defined — instance segmentation uses it for the visible parts of one occluded object, but the concept is general and not tied to any one use case.
_Avoid_: instance (it is only one application of grouping), cluster.

**Shape Conversion**:
Replacing a Shape's geometric kind (its `shape_type`) in place while keeping its identity — Label, Group, Shape Flags, and description. The UI verb is "Convert To", a submenu listing every Shape kind. A Conversion is either lossless (e.g. rectangle → polygon) or lossy (e.g. polygon → rectangle keeps only the bounding box); a lossy Conversion states what it discards at the point of use. Reverting relies on undo history, not on stored originals.
_Avoid_: turn into (it changes how content is presented, while a Conversion rewrites the geometry the user drew), transform, cast, change type.

**Mask Polygonization**:
Deriving one or more Polygon Shapes from a Mask, either while creating an AI Assist proposal or during Shape Conversion. Polygon Shapes from separate lands share a Group; holes are not represented.
_Avoid_: mask-to-points conversion, contour conversion

**AI Assist**:
Interactive, prompt-driven Shape proposal on the canvas: in AI-Segment the user places positive / negative points and draws a box on the Image, and a vision model (SAM, SAM2, EfficientSAM, SAM3) returns candidate Shapes. A prompt with points, with or without a box, contributes one candidate Shape, chosen by how well it satisfies the points and then by model confidence. A box-only prompt contributes the candidate that best fills the box; finding every object like the boxed one is AI-Find All. Candidates become new Shapes unless Existing Shape Suppression is enabled.
_Avoid_: AI annotation (too vague — covers AI-Find All too), auto-annotation, automation.

**Existing Shape Suppression**:
An optional AI Assist Setting for point prompts and box prompts. A candidate that matches an existing Shape highlights that Shape instead of creating a new Shape; unmatched candidates remain new Shapes. The Setting is disabled by default.
_Avoid_: duplicate suppression, overlap suppression.

**AI-Segment**:
The AI Assist tool that makes one Shape from positive points (click), negative points (Shift-click), and at most one box (drag), combined in any order. A new box replaces the previous one. Enter or a Ctrl-click makes the Shape.
_Avoid_: AI-Points, AI-Box (former tools it replaces), AI-Polygon, AI-Mask (older names of AI-Points).

**AI-Find All**:
Bulk Shape proposal for every matching instance in the Image. The user types one concept as the query, or draws a box around one example, and an open-vocabulary detector returns many candidate Shapes from one user action. The query is a prompt, not the label: one label entry, from the label dialog prefilled with the query, labels the whole batch, so "black dog" can be saved as "dog", and cancelling it discards the batch. Every batch, from a query or from example boxes, skips detections that overlap an existing Shape of the same Output with the label the batch takes, and reports how many it added. YOLO-World answers only text; SAM3 answers text and example boxes. Its candidates use the same Output as AI Assist. Example boxes build up: each new example, or counter-example drawn with Shift, re-runs the detection and replaces a draft of candidates. Enter asks for the batch's label and adds the draft as one undo step; Esc discards it.
_Avoid_: AI-Detect (former name; detection reads as boxes only), AI Text Prompt (the prompt is not only text), Sweep (retired name for the SAM3 example-box path), text-to-annotation (verbose), auto-detect (it always needs a prompt).

**Downloaded Model**:
A supported model whose required files are present in the local cache; every download is hash-checked before it lands there. It can be selected without a download; this does not guarantee hardware compatibility. Downloading from the AI Models window never selects a model. Choosing a model that is not downloaded in a toolbar model picker changes the Setting at that moment and queues its download; the choice takes effect when the files arrive. Completing a download never changes a selection or runs inference.
_Avoid_: installed model (confuses cached files with a loaded Model Session), available model (may mean merely listed in the catalog).

**Download Queue**:
The ordered list of models the user has explicitly requested from the AI Models window or a toolbar model picker. One model downloads at a time while Labelme stays open. Closing the window leaves downloads running; quitting stops the current transfer and discards the queue. Completed files are retained, and restarting downloads requires user action.
_Avoid_: background service (downloads do not outlive Labelme).

**Model Session**:
A loaded ML model that backs AI Assist or AI-Find All. One Model Session serves many proposals across the lifetime of the app. The legacy code directory `_automation/` hosts this layer.
_Avoid_: automation (legacy code-only term), backend, engine.

**Prompt Compatibility**:
The prompt kinds a Model Session can answer. A model can support point, box, or text prompts independently; selecting a model does not imply compatibility with every AI Assist mode.
_Avoid_: treating an unsupported prompt kind as an inference failure.

**Mask Shape**:
A Shape whose `shape_type` is `mask` — hybrid representation combining a rectangular bounding box (2 points) with a Mask (the raster pixels) that fills the bbox. The only `shape_type` that carries dense pixel data.
_Avoid_: raster shape, pixel polygon; do not say "mask" when you mean the whole Shape.

**Mask**:
The boolean pixel array inside a Mask Shape — one bit per pixel of the Mask Shape's bbox indicating whether the pixel belongs to the annotated region. Serialized as a base64-encoded PNG inside the Annotation File.
_Avoid_: bitmap, raster, segmentation map (when you mean just this Shape's pixels).

**Image**:
An input image file (PNG, JPEG, TIFF, etc.) that is the subject of an Annotation. Identified by its path on disk. The in-memory pixel array used while annotating is an implementation concern and not part of this term.
_Avoid_: photo, picture, file, frame.

**Image List**:
The dock listing the Images in this session. Opening a folder lists every Image under it, recursively; opening a single Image lists every Image under its parent folder the same way; opening an Annotation File directly empties and disables the list. A row's check mark means only that its Image has an Annotation File; users cannot toggle it. The dock keeps its legacy `file_dock` config key and `Files` object name, so saved layouts and Config Files still apply.
_Avoid_: file list.

**Label List**:
The dock listing the Labels in this session: the configured Labels (from the `--labels` CLI flag, a labels file, or the Config File) plus every Label used on a Shape since launch. It is append-only: a Label stays after its last Shape is deleted, so it is not the set of Labels on the current Image's Shapes. Label validation (`validate_label`) checks a new Label against it.
_Avoid_: labels (means the Labels on Shapes), label vocabulary (verbose), classes.

### Configuration

**Settings**:
The user-adjustable annotation and behavior values (auto-save, drawing colors, shortcuts, AI model, and so on). Each Setting is a *value*, not a control: the value is the source of truth (persisted in the Config File) and may be surfaced by more than one **Setting Control** at once, all bound to it and kept in sync.
_Avoid_: preferences (only the historical menu label), config (that is the file, not the values), options.

**Setting Control**:
A UI element bound to a Setting that displays and edits its value: a checkable menu/toolbar action, an inline dock control, or a widget in the Settings dialog. Inline controls are reserved for Settings toggled frequently or meaningful only in context; the Settings dialog is the comprehensive home that exposes every Setting. Multiple Setting Controls for one Setting stay in sync through a single apply path.
_Avoid_: toggle (only one kind), widget, knob.

**Preview Setting**:
A shipped Setting offered for early use while its interaction contract or presentation may still change. It meets normal data-safety and stability requirements and graduates after one stable release cycle with no known contract defects.
_Avoid_: beta feature, experimental option, beta setting.

**Polygon Detail**:
The 0–100 Setting that controls how closely a polygon follows the Shape it comes from, in Mask Polygonization and circle → polygon Shape Conversion. The allowed deviation is a fraction of the Shape's thickness (area / perimeter), so a value means the same at any Image resolution or Shape size (ADR 0010). Higher values retain more boundary detail, thinner lands, and Polygon Shape points; lower values produce smoother, simpler Polygon Shapes and omit lands much thinner than the Mask.
_Avoid_: polygon quality, smoothness, simplification tolerance

**Shape Color**:
The visual color used to distinguish a Shape. The Shape Color Mode determines whether Shapes use automatically assigned colors, one uniform color, or colors assigned per Label with a fallback.
_Avoid_: drawing color (also describes non-Shape canvas colors), label color (when referring to the Shape itself).

**Shape Color Mode**:
The Setting that selects automatic, uniform, or per-Label Shape Colors.
_Avoid_: color assignment, shape colors (when referring specifically to the mode choice).

**Config File**:
The on-disk YAML where Settings are persisted as sparse Overrides on top of the Default Config. Defaults to `~/.labelmerc`, but can be relocated, e.g. a `labelmerc` file beside the executable in standalone builds, or any path passed to `--config`. The file is called "config"; the values it carries are Settings.
_Avoid_: settings file, rc file, labelmerc.

**Default Config**:
The baseline Settings shipped in `labelme/_config/default_config.yaml`. Read-only, and the single source of both every default value and the set of allowed keys.
_Avoid_: defaults file, base config, schema.

**Override**:
A single Setting in the Config File whose value differs from the Default Config. The Config File holds only Overrides; resetting a Setting to its default removes its Override and keeps the file sparse.
_Avoid_: customization, change, diff.

**Window State**:
The window geometry and dock layout persisted via Qt's `QSettings` store (the `self._window_state` attribute in code), separate from Settings and never written to the Config File. Cleared by `--reset-config`.
_Avoid_: settings (those are the annotation/behavior values), config, layout config.

## Flagged ambiguities

- **`Annotation` / `LabelFile` in code**: the `Annotation` type names the in-memory **Annotation** (the whole bundle); it supersedes the former `LabelData`. The `LabelFile` class was removed; only the module and function names keep `label_file`. The Qt-free codec functions (`read_label_file` / `write_label_file`) and their module (`_label_file.py`) keep the `label_file` name for now; renaming them to `read_annotation_file` / `write_annotation_file` (in an `_annotation.py` module) is the matching deferred cleanup, best done together with the `LabelFile` → `AnnotationFile` rename so the module is renamed once.
- **Concept vs file naming is an intentional split**: the user-facing values are **Settings**, but the file that persists them is the **Config File** (`~/.labelmerc`) and the CLI flag stays `--config`. The menu entry reads "Settings…" while keeping Qt's `PreferencesRole`. Do not "unify" the file/flag/role naming to "settings".
- **`Shape` in code is the Qt-free data model**: the `Shape` type (`labelme/_shape/_model.py`) holds only data — `points` / `point_labels` are numpy arrays, not `QtCore.QPointF`, and it imports no PySide6. Hit-testing lives in `labelme/_shape/_hit_testing.py`. Rendering and the per-shape view state (selected, fill, highlight, colors, scale) live in the canvas layer (`_widgets/_shape_render.py` + `_widgets/_canvas.py`), which computes a `ShapeRenderContext` per shape at paint time. The in-progress shape being drawn is a separate QPointF `_DraftShape` (canvas-local) that becomes a `Shape` at finalize. `visible` is the one ephemeral view flag kept on `Shape` (a plain bool, not persisted) so it survives the deepcopy-based undo/backup stack.

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
> **N:** They also said their AI shapes disappear. They use AI-Find All — type "person", get a bunch of Shapes.
>
> **M:** Right. Those are still ordinary Shapes once the Model Session returns them; AI-Find All only produces them. After that they're stored in the Annotation File like any other Shape.
>
> **N:** They mentioned one Shape is a Mask Shape — does that change anything?
>
> **M:** Only the storage. A Mask Shape has a bbox plus an embedded Mask — the boolean pixel array, base64-encoded inside the Annotation File. If the file got truncated, the Mask is the most likely thing to be malformed.
>
> **N:** Last thing — they want Shapes from one occluded car to share a `group_id`. Is that an Instance?
>
> **M:** It's a Group. Instance segmentation is one application of grouping, but in our domain we just say Group. The Shapes share a `group_id` — that's all the data model knows about it.
