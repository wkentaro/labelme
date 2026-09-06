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
- [CAR JAM ESCAPE](https://learnquester.pages.dev/car-jam-escape.html)
- [CAR COLLISION MASTER](https://quizverses-9d2f2.web.app/car-collision-master.html)
- [HAPPY BLOCKS](https://quizverses.github.io/happy-blocks.html)
- [TROPICAL MATCH](https://quizverses.github.io/tropical-match.html)
- [SAMURAI MADNESS](https://studyquesthub.web.app/samurai-madness.html)
- [CATEGORY HERO](https://quizverses.github.io/category-hero.html)
- [ZOMBIE SHOOTING KING](https://studyquests.github.io/zombie-shooting-king.html)
- [CATEGORY BUBBLE SHOOTER27](https://studyquesthub.web.app/category-bubble-shooter27.html)
- [CRASH THE ROBOT](https://studyquests.github.io/crash-the-robot.html)
- [UNCLE HIT PUNCH THE DUMMY](https://quizverses.github.io/uncle-hit-punch-the-dummy.html)
- [FOOTBALL PENALTY 2026](https://studyquests.github.io/football-penalty-2026.html)
- [BULLET SUPERHERO](https://thelearnquesters.pages.dev/bullet-superhero.html)
- [THATS MY SEAT LOGIC PUZZLE](https://studyquests.github.io/thats-my-seat-logic-puzzle.html)
- [TYPE SPRINT](https://studyquests.github.io/type-sprint.html)
- [HEXA PUZZLE MASTER](https://quizverses.github.io/hexa-puzzle-master.html)
- [PRIVACY](https://quizverses.github.io/privacy.html)
- [ONET MAHJONG CONNECT](https://quizverses.github.io/onet-mahjong-connect.html)
- [CATEGORY SURVIVAL366](https://quizverses.github.io/category-survival366.html)
- [SWEET DESSERT HOLE](https://studyquests.github.io/sweet-dessert-hole.html)
- [CATEGORY SPACE](https://studyquesthub.web.app/category-space.html)
- [MAGIC BEAUTY MAKEUP](https://quizverses.github.io/magic-beauty-makeup.html)
- [BRIDGE FIGHT](https://quizverses.github.io/bridge-fight.html)
- [WARFRONT](https://studyquests.github.io/warfront.html)
- [ROBYBOX SPACE STATION WAREHOUSE](https://quizverses.github.io/robybox-space-station-warehouse.html)
- [PULL THE PIN FISH RESCUE](https://quizverses.github.io/pull-the-pin-fish-rescue.html)
- [2248 MUSICAL](https://quizverses.github.io/2248-musical.html)
- [LIMOUSINE CAR GAME SIMULATOR](https://studyquests.github.io/limousine-car-game-simulator.html)
- [CATEGORY CASUAL 4](https://quizverses-9d2f2.web.app/category-casual-4.html)
- [BUILD AND RUN](https://quizverses.github.io/build-and-run.html)
- [CATEGORY BLOCK94](https://quizverses-9d2f2.web.app/category-block94.html)
- [DREAM ROOM MAKEOVER](https://quizverses.github.io/dream-room-makeover.html)
- [SNAKE KING](https://studyquests.github.io/snake-king.html)
- [LOVE TILE TRIO](https://quizverses.github.io/love-tile-trio.html)
- [TANK BATTLEIO](https://quizverses.github.io/tank-battleio.html)
- [CAR PAINT](https://studyquests.github.io/car-paint.html)
- [CATEGORY LOGIC538](https://quizverses.github.io/category-logic538.html)
- [ICE CREAM INC](https://quizverses.github.io/ice-cream-inc.html)
- [RUNIC BLOCK COLLAPSE](https://studyquests.github.io/runic-block-collapse.html)
- [FURRY WEDDING PROPOSAL](https://quizverses.github.io/furry-wedding-proposal.html)
- [EPIC MINE](https://quizverses.github.io/epic-mine.html)
- [SCREW MATCH](https://studyquests.github.io/screw-match.html)
- [IDLE FIREFIGHTER 3D](https://studyquests.github.io/idle-firefighter-3d.html)
- [INDEX15](https://studyquesthub.web.app/index15.html)
- [CATEGORY MATCH 3117](https://studyplaying.github.io/category-match-3117.html)
- [STICKBOYS HOOK](https://studyquests.pages.dev/stickboys-hook.html)
- [HIGH HEELS COLLECT RUN](https://studyquests.github.io/high-heels-collect-run.html)
- [INDEX14](https://studyquesthub.web.app/index14.html)
- [ZENITH RUSH](https://studyquests.github.io/zenith-rush.html)
- [KINGDOM OF PIXELS](https://quizverses.github.io/kingdom-of-pixels.html)
- [HUNT AND SEEK](https://studyquests.github.io/hunt-and-seek.html)
- [DRAWING SQUARES](https://studyquesthub.web.app/drawing-squares.html)
- [NINJA OBBY PARKOUR](https://quizverses.github.io/ninja-obby-parkour.html)
- [ROPE SORTING](https://quizverses.github.io/rope-sorting.html)
- [GUN CLONE](https://quizverses.github.io/gun-clone.html)
- [CLEAN THE FLOOR](https://studyquests.github.io/clean-the-floor.html)
- [GENFIRE](https://studyquests.github.io/genfire.html)
- [BUNNYS FARM](https://studyquesthub.web.app/bunnys-farm.html)
- [ONLINE CAR DESTRUCTION SIMULATOR 3D](https://quizverses.github.io/online-car-destruction-simulator-3d.html)
- [2048 RUN GORGEOUS BALLS](https://quizverses.github.io/2048-run-gorgeous-balls.html)
- [CATEGORY DOG18](https://quizverses.github.io/category-dog18.html)
- [WORLD CUP SOCCER CAPS](https://quizverses.github.io/world-cup-soccer-caps.html)
- [CATEGORY MINECRAFT 2](https://studyplaying.github.io/category-minecraft-2.html)
- [TANK WARS IAW](https://quizverses.github.io/tank-wars-iaw.html)
- [TAIL GUN CHARLIE](https://quizverses.github.io/tail-gun-charlie.html)
- [MAGIC FOREST MERGE THE SECRETS](https://quizverses.github.io/magic-forest-merge-the-secrets.html)
- [IDLE INVENTOR](https://studyquesthub.web.app/idle-inventor.html)
- [CATEGORY DEFENSE](https://quizverses.github.io/category-defense.html)
- [CATEGORY COLOR197](https://quizverses.github.io/category-color197.html)
- [INDEX27](https://studyplaying.github.io/index27.html)
- [DIGIT SHOOTER](https://quizverses.github.io/digit-shooter.html)
- [CATEGORY BALL173](https://studyquesthub.web.app/category-ball173.html)
- [MOTO TRIALS RUSH](https://quizverses.github.io/moto-trials-rush.html)
- [CATEGORY HORROR](https://quizverses.github.io/category-horror.html)
- [VEGA MIX FAIRY TOWN](https://quizverses.pages.dev/vega-mix-fairy-town.html)
- [BOOM STICK BAZOOKA](https://studyquests.github.io/boom-stick-bazooka.html)
- [HERO FIGHT CLASH](https://quizverses-9d2f2.web.app/hero-fight-clash.html)
- [CUBE DROP PUZZLE](https://quizverses-9d2f2.web.app/cube-drop-puzzle.html)
- [CATEGORY BATTLE](https://studyquests.github.io/category-battle.html)
- [GOO GOO GAGA CLICKER](https://quizverses.pages.dev/goo-goo-gaga-clicker.html)
- [INSPECTOR CAT](https://quizverses-9d2f2.web.app/inspector-cat.html)
- [TB AVATARIA LIFE GIRL](https://quizverses.pages.dev/tb-avataria-life-girl.html)
- [INDEX21](https://studyplayings.web.app/index21.html)
- [HILL STATION BUS SIMULATOR](https://studyquests.github.io/hill-station-bus-simulator.html)
- [DRAW THE WEAPON](https://quizverses.pages.dev/draw-the-weapon.html)
- [CATEGORY MOBILE2 112](https://studyplaying.github.io/category-mobile2-112.html)
- [IDLE BATHROOM EMPIRE TYCOON](https://quizverses.github.io/idle-bathroom-empire-tycoon.html)
- [HIGHSCHOOL MEAN GIRLS 3](https://learnquester.pages.dev/highschool-mean-girls-3.html)
- [CATEGORY MAKEUP51](https://thelearnquester.web.app/category-makeup51.html)
- [PYRAMIDZ](https://quizverses.github.io/pyramidz.html)
- [SUIKA KAWAII CAT MERGE GAME](https://quizverses.github.io/suika-kawaii-cat-merge-game.html)
- [BASKET SWAP](https://quizverses.github.io/basket-swap.html)
- [CRAZY VAN](https://studyplayings.pages.dev/crazy-van.html)
- [SPACE BLAST](https://studyquests.github.io/space-blast.html)
- [CATEGORY SIDE SCROLLING184](https://thelearnquester.web.app/category-side-scrolling184.html)
- [CATEGORY MAHJONG37](https://studyquests.github.io/category-mahjong37.html)
- [VALENTINES DAY COUPLE DATE](https://studyquesthub.web.app/valentines-day-couple-date.html)
- [TERMS](https://studyplaying.github.io/terms.html)
- [CATEGORY RAGDOLL57](https://learnquester.github.io/category-ragdoll57.html)
- [BULLET SUPERHERO](https://quizverses.github.io/bullet-superhero.html)
- [CATEGORY FASHION105](https://learnquester.pages.dev/category-fashion105.html)
- [VEX HYPER DASH](https://quizverses.github.io/vex-hyper-dash.html)
- [CATEGORY SOCCER](https://quizverses.pages.dev/category-soccer.html)
- [SUDOKU BRAIN BLOCKS](https://studyquests.github.io/sudoku-brain-blocks.html)
- [OCEAN KIDS BACK TO SCHOOL](https://quizverses.pages.dev/ocean-kids-back-to-school.html)
- [TAP GO DELUXE](https://quizverses.github.io/tap-go-deluxe.html)
- [AGENT HUNT SPY SHOOTER GAME](https://studyquests.github.io/agent-hunt-spy-shooter-game.html)
- [CAT MATCH 3](https://studyplayings.pages.dev/cat-match-3.html)
- [CATEGORY UNBLOCKED](https://learnquester.pages.dev/category-unblocked.html)
- [FASHION VALKYRIES SAGA OF STYLE](https://studyquests.pages.dev/fashion-valkyries-saga-of-style.html)
- [BRAINROT EVOLUTION GAME](https://quizverses-9d2f2.web.app/brainrot-evolution-game.html)
- [FINGER HEART MONSTER REFILL](https://quizverses.github.io/finger-heart-monster-refill.html)
- [BRAINROT A DIFFERENCE CHALLENGE](https://learnquester.pages.dev/brainrot-a-difference-challenge.html)
- [2048 BLOCK FUSION](https://studyquests.github.io/2048-block-fusion.html)
- [PET DOCTOR BUSINESS TYCOON PET CARE GAME](https://studyquests.github.io/pet-doctor-business-tycoon-pet-care-game.html)
- [CATEGORY MAHJONG GAMES](https://thelearnquester.web.app/category-mahjong-games.html)
- [CATEGORY UNBLOCKED](https://thelearnquester.web.app/category-unblocked.html)
- [TILE SORT MATCH 3](https://studyplaying.github.io/tile-sort-match-3.html)
- [NUMBER DOMINATION](https://studyplayings.pages.dev/number-domination.html)
- [CATEGORY ESCAPE187](https://studyquests.github.io/category-escape187.html)
- [MERGE MUSCLE](https://studyquests.github.io/merge-muscle.html)
- [MOJICON GARDEN CONNECT](https://quizverses.github.io/mojicon-garden-connect.html)
- [RAGDOLL ARENA 2 PLAYER](https://studyplayings.pages.dev/ragdoll-arena-2-player.html)
- [PUZZLE MASTERS TRAVELERS](https://quizverses.github.io/puzzle-masters-travelers.html)
- [NUMBER DOMINATION](https://quizverses.github.io/number-domination.html)
- [SNAKE 2048](https://studyquesthub.web.app/snake-2048.html)
- [LITTLE CANDY BAKERY](https://studyplaying.github.io/little-candy-bakery.html)
- [HIGHWAY BUS RUSH](https://studyquests.pages.dev/highway-bus-rush.html)
- [CATEGORY MERGE221](https://thelearnquester.web.app/category-merge221.html)
- [CATEGORY SPORTS](https://thelearnquester.web.app/category-sports.html)
- [CATEGORY MONSTER](https://learnquester.github.io/category-monster.html)
