# Labelme

Labelme is a desktop application for drawing structured annotations on images.
It supports common geometric shapes, image-level flags, configurable label rules,
and assisted annotation models.

## Install

The Python package supports Python 3.12 through 3.14:

```bash
python -m pip install labelme
```

A standalone desktop build is available from [labelme.io](https://labelme.io) for
people who do not want to manage a Python environment.

Linux distributions may also package Labelme. The current package inventory is on
[Repology](https://repology.org/project/labelme/versions).

## Start annotating

Launch an empty session or open a file or directory:

```bash
labelme
labelme photo.jpg
labelme images/
```

Annotations are JSON files. By default each JSON file is written beside its image.
Use `--output` when annotations should live in a separate directory:

```bash
labelme images/ --output annotations/
```

Pass labels inline or in a UTF-8 text file containing one label per line:

```bash
labelme images/ --labels cat,dog,person
labelme images/ --labels labels.txt
```

Run `labelme --help` for authoritative usage. The main options are:

| Option | Purpose |
| --- | --- |
| `PATH` | Open an image, annotation JSON file, or image directory. |
| `--output DIR` | Store annotation JSON files in `DIR`. |
| `--config PATH_OR_YAML` | Load settings from a YAML file or inline YAML. |
| `--with-image-data` | Embed the source image bytes in each annotation. |
| `--no-auto-save` | Require an explicit save action. |
| `--no-sort-labels` | Keep labels in the supplied order. |
| `--flags LIST_OR_FILE` | Define image-level flags. |
| `--label-flags YAML_OR_FILE` | Define label-specific flags. |
| `--labels LIST_OR_FILE` | Define the available shape labels. |
| `--validate-label exact` | Reject labels outside the supplied list. |
| `--keep-prev` | Seed an unannotated image from the previous image. |
| `--epsilon FLOAT` | Set the pointer hit tolerance in screen pixels. |
| `--logger-level LEVEL` | Select debug, info, warning, error, or critical logs. |
| `--reset-config` | Clear saved window geometry and layout, then exit. |
| `--version` | Print the installed version and exit. |

## Interface language

Choose a language under **Settings → Appearance and language → Language**, then
restart Labelme. **System default** follows your operating system; **English**
always uses the source interface. Twenty translated languages are bundled.

You can also set a locale in the configuration file, for example `language: ja_JP`.

## Supported annotation workflows

- Polygon, rectangle, oriented rectangle, circle, line, line strip, and point shapes
- Image classification through flags
- Directory and video-frame annotation
- VOC and COCO conversion examples
- Point, box, and text-assisted annotation models

The scripts under [`examples/`](examples) operate on user-supplied images and
annotations. Each example README describes its expected input and generated output.

## Stable interfaces

The supported integration boundaries are the command-line interface, the JSON
annotation format, and the YAML configuration format. Modules inside the Python
package are implementation details and may change without compatibility guarantees.

Version 7 requires Python 3.12+, PySide6, and a 64-bit supported operating system.
Users who require Python 3.10, Python 3.11, or Qt 5 can pin the maintenance series:

```bash
python -m pip install 'labelme<7'
```

## Build a desktop bundle

Install Labelme and PyInstaller in the same environment, then collect their packaged
data:

```bash
LABELME_PATH=$(python -c 'import pathlib, labelme; print(pathlib.Path(labelme.__file__).parent)')
LABELME_ENTRY=$(command -v labelme)
pyinstaller "$LABELME_ENTRY" \
  --name Labelme \
  --windowed \
  --noconfirm \
  --icon "$LABELME_PATH/icons/phosphor/app.png" \
  --collect-data labelme \
  --collect-data osam \
  --onedir
```

## Project history

This project began as a fork of
[`mpitid/pylabelme`](https://github.com/mpitid/pylabelme).
