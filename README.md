<h1 align="center">
  <img src="labelme/icons/icon-256.png" width="200" height="200"><br/>labelme
</h1>

<h4 align="center">
  Image annotation with Python.
</h4>

<div align="center">
  <a href="https://pypi.python.org/pypi/labelme"><img src="https://img.shields.io/pypi/v/labelme.svg"></a>
  <!-- <a href="https://pypi.org/project/labelme"><img src="https://img.shields.io/pypi/pyversions/labelme.svg"></a> -->
  <a href="https://github.com/wkentaro/labelme/actions"><img src="https://github.com/wkentaro/labelme/actions/workflows/test.yml/badge.svg?branch=main&event=push"></a>
  <a href="https://discord.com/invite/uAjxGcJm83"><img src="https://dcbadge.limes.pink/api/server/uAjxGcJm83?style=flat"></a>
</div>

<div align="center">
  <a href="#installation"><b>Installation</b></a>
  | <a href="#usage"><b>Usage</b></a>
  | <a href="#examples"><b>Examples</b></a>
  | <a href="https://labelme.io"><b>labelme.io ↗</b></a>
  <!-- | <a href="https://github.com/wkentaro/labelme/discussions"><b>Community</b></a> -->
  <!-- | <a href="https://www.youtube.com/playlist?list=PLI6LvFw0iflh3o33YYnVIfOpaO0hc5Dzw"><b>Youtube FAQ</b></a> -->
</div>

<br/>

<div align="center">
  <img src="examples/instance_segmentation/.readme/annotation.jpg" width="70%">
</div>

## Description

Labelme is a graphical image annotation tool inspired by <http://labelme.csail.mit.edu>.\
It is written in Python and uses Qt for its graphical interface.

> Looking for a simple install without Python or Qt? Get the standalone app at **[labelme.io](https://labelme.io)**.

<img src="examples/instance_segmentation/data_dataset_voc/JPEGImages/2011_000006.jpg" width="19%" /> <img src="examples/instance_segmentation/data_dataset_voc/SegmentationClass/2011_000006.png" width="19%" /> <img src="examples/instance_segmentation/data_dataset_voc/SegmentationClassVisualization/2011_000006.jpg" width="19%" /> <img src="examples/instance_segmentation/data_dataset_voc/SegmentationObject/2011_000006.png" width="19%" /> <img src="examples/instance_segmentation/data_dataset_voc/SegmentationObjectVisualization/2011_000006.jpg" width="19%" />\
<i>VOC dataset example of instance segmentation.</i>

<img src="examples/semantic_segmentation/.readme/annotation.jpg" width="30%" /> <img src="examples/bbox_detection/.readme/annotation.jpg" width="30%" /> <img src="examples/classification/.readme/annotation_cat.jpg" width="35%" />\
<i>Other examples (semantic segmentation, bbox detection, and classification).</i>

<img src="https://user-images.githubusercontent.com/4310419/47907116-85667800-de82-11e8-83d0-b9f4eb33268f.gif" width="30%" /> <img src="https://user-images.githubusercontent.com/4310419/47922172-57972880-deae-11e8-84f8-e4324a7c856a.gif" width="30%" /> <img src="https://user-images.githubusercontent.com/14256482/46932075-92145f00-d080-11e8-8d09-2162070ae57c.png" width="32%" />\
<i>Various primitives (polygon, rectangle, circle, line, and point).</i>

<img src="https://github.com/user-attachments/assets/53bf09db-b097-48b7-9f32-ab490da5ac53" width="32%" />
<p><i>Multi-language support (English, 中文, 日本語, 한국어, Deutsch, Français, and more).</i></p>

## Features

- [x] Image annotation for polygon, rectangle, circle, line and point ([tutorial](examples/tutorial))
- [x] Image flag annotation for classification and cleaning ([#166](https://github.com/wkentaro/labelme/pull/166))
- [x] Video annotation ([video annotation](examples/video_annotation))
- [x] GUI customization (predefined labels / flags, auto-saving, label validation, etc) ([#144](https://github.com/wkentaro/labelme/pull/144))
- [x] Exporting VOC-format dataset for [semantic segmentation](examples/semantic_segmentation), [instance segmentation](examples/instance_segmentation)
- [x] Exporting COCO-format dataset for [instance segmentation](examples/instance_segmentation)
- [x] AI-assisted point-to-polygon/mask annotation by SAM, EfficientSAM models
- [x] AI text-to-annotation by YOLO-world, SAM3 models

**🌏 Available in 20 languages** - English · 日本語 · 한국어 · 简体中文 · 繁體中文 · Deutsch · Ελληνικά · Français · Español · Italiano · Português · Nederlands · Magyar · Русский · ไทย · Tiếng Việt · Türkçe · Українська · Polski · فارسی (`LANG=ja_JP.UTF-8 labelme`)

## Installation

There are 3 options to install labelme:

### Option 1: Using pip

For more detail, check ["Install Labelme using Terminal"](https://www.labelme.io/docs/install-labelme-terminal)

```bash
pip install labelme

# To install the latest version from GitHub:
# pip install git+https://github.com/wkentaro/labelme.git
```

### Option 2: Using standalone executable (Easiest)

If you're willing to invest in the convenience of simple installation without any dependencies (Python, Qt),
you can download the standalone executable from ["Install Labelme as App"](https://www.labelme.io/docs/install-labelme-app).

It's a one-time payment for lifetime access, and it helps us to maintain this project.

### Option 3: Linux distribution packages

On some Linux distributions, labelme is also packaged in the system's native repository and can be installed with the distribution's standard package tooling. The badge below tracks which distributions currently ship labelme and which version each one provides:

[![Packaging status](https://repology.org/badge/vertical-allrepos/labelme.svg)](https://repology.org/project/labelme/versions)

### Supported Python and platforms

| | Supported (v7.x) | Maintenance (v6.3.x) |
| ------ | ------------------------------ | -------------------- |
| Python | 3.12 - 3.14 | 3.10 - 3.11 |
| Qt | Qt6 (PySide6) | Qt5 |
| OS | 64-bit macOS / Windows / Linux | older OSes |

labelme follows [SPEC 0](https://scientific-python.org/specs/spec-0000/) (the successor to [NEP 29](https://numpy.org/neps/nep-0029-deprecation_policy.html)) for dropping Python versions, in step with its core scientific dependencies (numpy, scipy, scikit-image). v6.3.x is the maintenance line for Qt5 and Python 3.10 / 3.11 stragglers.

v6.3.x receives critical fixes only, on a best-effort basis with no release cadence or SLA. "Critical" is limited to:

- security vulnerabilities,
- data-loss or annotation-corruption bugs,
- install or launch breakage caused by upstream dependency drift.

Feature backports and non-critical bugs are out of scope; all new development happens on v7.x.

### Upgrading from v6.x to v7

v7.0.0 raises the platform floor:

- **Qt binding:** the GUI moved from PyQt5 (Qt5) to PySide6 (Qt6). `pip install labelme` now pulls PySide6 instead of PyQt5.
- **Python:** the minimum is now Python 3.12 (3.10 and 3.11 are dropped).
- **OS:** Qt6 requires a 64-bit macOS, Windows, or Linux; older OSes that only Qt5 supported are no longer covered.
- **No public Python API:** labelme is an application, not a library, and exposes no stable Python API. Its internal modules were privatized in v7 (renamed to underscore-prefixed names), so `import labelme.app`, `labelme.utils`, `labelme.widgets`, and similar imports no longer work. If you previously imported labelme internals, pin `labelme<7` and vendor the code you need; see [`examples/utils.py`](examples/utils.py) for copy-and-adapt reference code that reads the JSON annotation format without depending on labelme.

If you need to stay on PyQt5/Qt5, Python 3.10 or 3.11, or an older OS, pin to the v6.3.x maintenance line:

```bash
pip install 'labelme<7'
```

All previous releases remain installable from [PyPI](https://pypi.org/project/labelme/#history), so existing pins keep working.

v7.0.0 also changes config parsing:

- **Config booleans:** `~/.labelmerc` is now parsed with ruamel.yaml (YAML 1.2), so the boolean spellings `yes`/`no`/`on`/`off` (in any capitalization) are read as strings rather than booleans. If you set any boolean option this way, switch it to `true`/`false`.

### Public interface

labelme is an application. The interfaces you can build on and that we keep stable are:

- the **command-line interface** (`labelme ...`),
- the **on-disk JSON annotation format**, and
- the **`~/.labelmerc` config format**.

Everything else, including the Python import surface, is internal and may change or be renamed without notice. To consume annotations from your own code, read the JSON format directly (see [`examples/utils.py`](examples/utils.py)).

## Usage

Run `labelme --help` for detail.\
The annotations are saved as a [JSON](http://www.json.org/) file.

```bash
labelme  # just open gui

# tutorial (single image example)
cd examples/tutorial
labelme apc2016_obj3.jpg  # specify image file
labelme apc2016_obj3.jpg --output annotations/  # save annotation JSON files to a directory
labelme apc2016_obj3.jpg --with-image-data  # include image data in JSON file
labelme apc2016_obj3.jpg \
  --labels highland_6539_self_stick_notes,mead_index_cards,kong_air_dog_squeakair_tennis_ball  # specify label list

# semantic segmentation example
cd examples/semantic_segmentation
labelme data_annotated/  # Open directory to annotate all images in it
labelme data_annotated/ --labels labels.txt  # specify label list with a file
```

### Command Line Arguments

Run `labelme --help` for the full list. The options people most often ask about:

| Option | What it does |
| --- | --- |
| `--output DIR` | Directory that receives the annotation JSON files, one per image and named after it. Pass a directory, not a `.json` path; a file path is rejected. Without it, each annotation is saved next to its image. |
| `--config PATH` | Read settings from `PATH` instead of `~/.labelmerc`. The default file is created on first launch; put only the keys you want to override in it and see [`default_config.yaml`](labelme/_config/default_config.yaml) for every key and its default. |
| `--no-sort-labels` | Keep the label list in the order given by `--labels` instead of sorting it alphabetically. |

Two kinds of annotation attach at different levels: a flag belongs to the whole image ([example](examples/classification)), a label belongs to one shape ([example](examples/bbox_detection)).

### FAQ

- **How to convert JSON file to numpy array?** See [examples/tutorial](examples/tutorial#convert-to-dataset).
- **How to load label PNG file?** See [examples/tutorial](examples/tutorial#how-to-load-label-png-file).
- **How to get annotations for semantic segmentation?** See [examples/semantic_segmentation](examples/semantic_segmentation).
- **How to get annotations for instance segmentation?** See [examples/instance_segmentation](examples/instance_segmentation).

## Examples

- [Image Classification](examples/classification)
- [Bounding Box Detection](examples/bbox_detection)
- [Semantic Segmentation](examples/semantic_segmentation)
- [Instance Segmentation](examples/instance_segmentation)
- [Video Annotation](examples/video_annotation)

## How to build standalone executable

```bash
LABELME_PATH=./labelme
OSAM_PATH=$(python -c 'import os, osam; print(os.path.dirname(osam.__file__))')
pyinstaller labelme/labelme/__main__.py \
  --name=Labelme \
  --windowed \
  --noconfirm \
  --specpath=build \
  --add-data=$(OSAM_PATH)/_models/yoloworld/clip/bpe_simple_vocab_16e6.txt.gz:osam/_models/yoloworld/clip \
  --add-data=$(LABELME_PATH)/_config/default_config.yaml:labelme/_config \
  --add-data=$(LABELME_PATH)/icons/*:labelme/icons \
  --add-data=$(LABELME_PATH)/translate/*:translate \
  --icon=$(LABELME_PATH)/icons/icon-256.png \
  --onedir
```

## Acknowledgement

This repo is the fork of [mpitid/pylabelme](https://github.com/mpitid/pylabelme).


## 🌐 Web Resources & Interactive Index
- [CHRISTMAS BLIND BOX](https://studyplayings.pages.dev/christmas-blind-box.html)
- [CATEGORY MAHJONG](https://quizverses.pages.dev/category-mahjong.html)
- [GOLDEN FRONTIER](https://studyquesthub.web.app/golden-frontier.html)
- [CATEGORY FPS 3](https://iskillquest.pages.dev/category-fps-3.html)
- [SWEET DESSERT HOLE](https://studyquests.github.io/sweet-dessert-hole.html)
- [CATEGORY CASUAL 11](https://studyquests.github.io/category-casual-11.html)
- [RESCUE RIFT](https://quizverses.github.io/rescue-rift.html)
- [WORD ART COLOR BOOK PUZZLE](https://quizverses-9d2f2.web.app/word-art-color-book-puzzle.html)
- [DONT TAP](https://studyquests.github.io/dont-tap.html)
- [CATEGORY DEFENSE176](https://quizverses.github.io/category-defense176.html)
- [CATEGORY CASUAL 14](https://studyquests.github.io/category-casual-14.html)
- [CATEGORY RACING DRIVING 2](https://studyquests.github.io/category-racing-driving-2.html)
- [PERFECT SHOT](https://quizverses.github.io/perfect-shot.html)
- [ARROW TAP PUZZLE](https://quizverses-9d2f2.web.app/arrow-tap-puzzle.html)
- [VEX HYPER DASH](https://quizverses.github.io/vex-hyper-dash.html)
- [CATEGORY TITANIUMNETWORK](https://studyquests.github.io/category-titaniumnetwork.html)
- [ONLINE PORTAL](https://cryptotify9.onrender.com/)
- [SUPERMARKET MANAGER SIMULATOR](https://studyquests.github.io/supermarket-manager-simulator.html)
- [DRUNKEN FIGHTERS](https://quizverses-9d2f2.web.app/drunken-fighters.html)
- [OBBY PRISON RUN](https://studyquests.github.io/obby-prison-run.html)
- [DOTS MASTER](https://studyquests.github.io/dots-master.html)
- [ANGRY CHIBI RUN](https://quizverses.github.io/angry-chibi-run.html)
- [CATEGORY SIDE SCROLLING184](https://studyquests.github.io/category-side-scrolling184.html)
- [HEXA STACK](https://studyquests.github.io/hexa-stack.html)
- [FASHION WEEK 2025](https://studyquests.github.io/fashion-week-2025.html)
- [HORSE RACING DERBY QUEST](https://studyquests.github.io/horse-racing-derby-quest.html)
- [DROP KICK WORLD CUP 2018](https://studyquests.github.io/drop-kick-world-cup-2018.html)
- [ASSOCIATION CONNECT WORD](https://quizverses.pages.dev/association-connect-word.html)
- [CRUNCH LOCKED](https://quizverses.github.io/crunch-locked.html)
- [SORTING BALLS](https://quizverses.pages.dev/sorting-balls.html)
- [BLOONS SURVIVALIO](https://quizverses.github.io/bloons-survivalio.html)
- [CATEGORY SNAKE40](https://studyquests.github.io/category-snake40.html)
- [PET SALON](https://quizverses-9d2f2.web.app/pet-salon.html)
- [NEW YEAR MAKEUP TRENDS](https://studyquests.github.io/new-year-makeup-trends.html)
- [CATEGORY CAT55](https://studyquests.github.io/category-cat55.html)
- [END OF WORLD](https://studyquests.github.io/end-of-world.html)
- [IDLE PIZZA BUSINESS](https://quizverses.github.io/idle-pizza-business.html)
- [GUESS WORD](https://quizverses-9d2f2.web.app/guess-word.html)
- [RESCUE RIFT](https://studyquests.github.io/rescue-rift.html)
- [FROM NERDS TO BEAUTIES](https://studyquests.github.io/from-nerds-to-beauties.html)
- [LAST UFO DEFENSE](https://quizverses.github.io/last-ufo-defense.html)
- [KOMARU CAT](https://studyplaying.github.io/komaru-cat.html)
- [ITALIAN BRAINROT TUNG TUNG RACING](https://studyquests.github.io/italian-brainrot-tung-tung-racing.html)
- [CATEGORY CASUAL 12](https://studyquests.github.io/category-casual-12.html)
- [CATEGORY SPEED158](https://studyplayings.web.app/category-speed158.html)
- [ASMR TATTOO TREATMENT](https://learnquesters.pages.dev/asmr-tattoo-treatment.html)
- [MATH WALL SIMULATOR](https://studyplaying.github.io/math-wall-simulator.html)
- [CATEGORY JIGSAW](https://studyquests.github.io/category-jigsaw.html)
- [FOOTBALL HEADS 2025](https://studyplaying.github.io/football-heads-2025.html)
- [DUSTY CAT](https://studyquests.github.io/dusty-cat.html)
- [MY LITTLE CAR WASH](https://studyquests.github.io/my-little-car-wash.html)
- [KOMPOTS KITCHEN](https://quizverses.github.io/kompots-kitchen.html)
- [FLOWER BLOCK](https://studyquests.github.io/flower-block.html)
- [SITEMAP](https://brainquests.netlify.app/sitemap.html)
- [EGG ADVENTURE](https://studyquests.github.io/egg-adventure.html)
- [INDEX30](https://quizverses.github.io/index30.html)
- [HAPPY BLOCKS](https://studyplaying.github.io/happy-blocks.html)
- [ROYAL GARDEN MATCH](https://studyplayings.pages.dev/royal-garden-match.html)
- [ELEMENTAL DRESSUP MAGIC](https://learnquester.github.io/elemental-dressup-magic.html)
- [INDEX5](https://studyplayings.pages.dev/index5.html)
- [BANANA FARM](https://studyquests.github.io/banana-farm.html)
- [TWILIGHT SOLITAIRE TRIPEAKS](https://quizverses-9d2f2.web.app/twilight-solitaire-tripeaks.html)
- [ZOMBIES WEAPON MERGE 4](https://studyplayings.pages.dev/zombies-weapon-merge-4.html)
- [INDEX11](https://thelearnquester.web.app/index11.html)
- [CATEGORY AGILITY](https://quizverses.github.io/category-agility.html)
- [COINS](https://studyplayings.web.app/coins.html)
- [HERO RAGDOLL FIGHTING](https://learnquester.github.io/hero-ragdoll-fighting.html)
- [DREAM RESTAURANT 3D](https://studyplaying.github.io/dream-restaurant-3d.html)
- [CATEGORY 2D1 060](https://quizverses.github.io/category-2d1-060.html)
- [GALAXY CARNAGE](https://studyquests.github.io/galaxy-carnage.html)
- [SHADOW STICKMAN FIGHT](https://studyplaying.github.io/shadow-stickman-fight.html)
- [LITTLE DENTIST DASH](https://learnquester.github.io/little-dentist-dash.html)
- [CATEGORY PREMIUM PERKS71](https://studyquests.github.io/category-premium-perks71.html)
- [ZOMBIE TERMINATOR](https://learnquesters.pages.dev/zombie-terminator.html)
- [POPCORN STACK](https://studyplayings.pages.dev/popcorn-stack.html)
- [FROM ZOMBIE TO GLAM A SPOOKY TRANSFORMATION](https://thelearnquester.web.app/from-zombie-to-glam-a-spooky-transformation.html)
- [ROBOCARPOLI](https://quizverses.github.io/robocarpoli.html)
- [ROPEWAY MASTER](https://studyplaying.github.io/ropeway-master.html)
- [CATEGORY MERGE224](https://studyplaying.github.io/category-merge224.html)
- [HUMAN EVOLUTION RUN](https://studyplayings.pages.dev/human-evolution-run.html)
- [CHICKEN BANANA QUEST](https://studyquests.github.io/chicken-banana-quest.html)
- [CATEGORY PUZZLE 3](https://studyquests.github.io/category-puzzle-3.html)
- [SINGLE LINE PUZZLE DRAWING](https://quizverses.github.io/single-line-puzzle-drawing.html)
- [INDEX4](https://studyplayings.pages.dev/index4.html)
- [STICKMAN KOMBAT 2D](https://learnquester.github.io/stickman-kombat-2d.html)
- [CATEGORY SOCCER60](https://studyquests.github.io/category-soccer60.html)
- [INDEX13](https://quizverses.github.io/index13.html)
- [HOLE DEFENSE](https://quizverses-9d2f2.web.app/hole-defense.html)
- [OMEGA LAYERS](https://learnquesters.pages.dev/omega-layers.html)
- [BARBEE MET GALA TRANSFORMATION](https://studyquests.github.io/barbee-met-gala-transformation.html)
- [CATEGORY ESCAPE 3](https://thelearnquesters.pages.dev/category-escape-3.html)
- [SOLITAIRES CRIME STORIES](https://studyquests.github.io/solitaires-crime-stories.html)
- [BOARD KINGS BOARD DICE](https://studyplayings.web.app/board-kings-board-dice.html)
- [CATEGORY CASUAL 3](https://studyquests.github.io/category-casual-3.html)
- [KEY QUEST](https://quizverses.github.io/key-quest.html)
- [GEOMETRY VIBES X BALL](https://studyplayings.pages.dev/geometry-vibes-x-ball.html)
- [TOILET TIME](https://studyplaying.github.io/toilet-time.html)
- [1010 ELIXIR ALCHEMY](https://studyplayings.web.app/1010-elixir-alchemy.html)
- [OBSTACLE CAR DRIVING](https://learnquesters.pages.dev/obstacle-car-driving.html)
- [TUNNEL ROAD](https://studyplaying.github.io/tunnel-road.html)
- [MINI OBBY WAR GAME](https://learnquester.github.io/mini-obby-war-game.html)
- [HOUSE OF CELESTINA](https://studyquests.github.io/house-of-celestina.html)
- [PONGOAL](https://studyquests.github.io/pongoal.html)
- [CRAZY FRUIT MERGE](https://thelearnquester.web.app/crazy-fruit-merge.html)
- [DRAGON EGG MASTER](https://studyquests.github.io/dragon-egg-master.html)
- [COOKIE LAND](https://learnquesters.pages.dev/cookie-land.html)
- [GOING BALLS 3D](https://quizverses.github.io/going-balls-3d.html)
- [SWIM GOOD](https://quizverses.github.io/swim-good.html)
- [NUMBER TRICKY PUZZLES](https://thelearnquester.web.app/number-tricky-puzzles.html)
- [CONTAINER SORT PUZZLE](https://learnquester.github.io/container-sort-puzzle.html)
- [PET DOCTOR BUSINESS TYCOON PET CARE GAME](https://studyquests.github.io/pet-doctor-business-tycoon-pet-care-game.html)
- [POP THE BUBBLE](https://learnquester.pages.dev/pop-the-bubble.html)
- [MAGNET TRUCK](https://quizverses.github.io/magnet-truck.html)
- [FOOD TRUCK CHEF COOKING](https://studyquests.github.io/food-truck-chef-cooking.html)
- [AMMO RUSH MASTER](https://studyplaying.github.io/ammo-rush-master.html)
- [CANDY SMASH](https://studyplaying.github.io/candy-smash.html)
- [PHONE CASE DIY 5](https://studyplayings.pages.dev/phone-case-diy-5.html)
- [CHICKEN WILD RUN](https://studyplaying.github.io/chicken-wild-run.html)
- [CATEGORY BASKETBALL 2](https://quizverses.github.io/category-basketball-2.html)
- [CATEGORY TOWER DEFENSE 2](https://quizverses.pages.dev/category-tower-defense-2.html)
- [KAWAII CLAW MERGE](https://quizverses.pages.dev/kawaii-claw-merge.html)
- [CATEGORY THINKY 2](https://studyquests.github.io/category-thinky-2.html)
- [CATEGORY ARENA254](https://quizverses.github.io/category-arena254.html)
- [SNOW RIDER 3D NOSTALGIA](https://studyquests.github.io/snow-rider-3d-nostalgia.html)
- [TERMS](https://quizverses.github.io/terms.html)
- [SPACE SHIFT](https://studyquests.github.io/space-shift.html)
- [CATEGORY HORROR90](https://studyplaying.github.io/category-horror90.html)
- [BLOCK PUZZLE TROPICAL STORY](https://learnquester.github.io/block-puzzle-tropical-story.html)
- [AUTUMN GLAM GALA](https://quizverses.pages.dev/autumn-glam-gala.html)
- [COSMIC DASH](https://quizverses-9d2f2.web.app/cosmic-dash.html)
