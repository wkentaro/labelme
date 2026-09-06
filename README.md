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
- [MEAN GIRLS GRADUATION DAY](https://studyplayings.web.app/mean-girls-graduation-day.html)
- [ANACONDA RUNNER](https://studyquests.github.io/anaconda-runner.html)
- [WENDY SOFT GIRL MAKEUP](https://learnquesters.pages.dev/wendy-soft-girl-makeup.html)
- [TATTOO MASTER](https://thelearnquester.web.app/tattoo-master.html)
- [PUZZLE BLOCKS ASMR MATCH](https://themindzone.pages.dev/puzzle-blocks-asmr-match.html)
- [ERASE THE EXTRA ELEMENT](https://theskillquest.pages.dev/erase-the-extra-element.html)
- [GALAXY CLICKER](https://themindzone.pages.dev/galaxy-clicker.html)
- [TILES MATCHING](https://themindzone.pages.dev/tiles-matching.html)
- [ITALIAN BRAINROT QUIZ](https://iskillquest.pages.dev/italian-brainrot-quiz.html)
- [BATTLE ISLAND 2](https://themindzone.pages.dev/battle-island-2.html)
- [TRIANGLES](https://themindzone.pages.dev/triangles.html)
- [BUNNY BOY ONLINE](https://themindzone.pages.dev/bunny-boy-online.html)
- [ASMR PET TREATMENT](https://themindzone.pages.dev/asmr-pet-treatment.html)
- [CATEGORY SIMULATION](https://learnquester.pages.dev/category-simulation.html)
- [CIRCUIT MASTER](https://thequizzone.pages.dev/circuit-master.html)
- [BATTLE OF PIRATE CARIBBEAN BATTLE](https://themindzone.pages.dev/battle-of-pirate-caribbean-battle.html)
- [STICKMAN DINOSAUR ARENA](https://themindzone.pages.dev/stickman-dinosaur-arena.html)
- [POWERFUL PUNCH](https://themindzone.pages.dev/powerful-punch.html)
- [ICONIC HALLOWEEN COSTUMES](https://thequizzone.pages.dev/iconic-halloween-costumes.html)
- [LEAP AND AVOID 2](https://themindzone.pages.dev/leap-and-avoid-2.html)
- [CATEGORY CUTE](https://thequizzone.pages.dev/category-cute.html)
- [STICKMAN DUO ESCAPE THE TOMB](https://thelearnquester.web.app/stickman-duo-escape-the-tomb.html)
- [DIVINEX](https://themindzone.pages.dev/divinex.html)
- [ARROWS PUZZLE ESCAPE](https://themindzone.pages.dev/arrows-puzzle-escape.html)
- [SUPERWINGS SUBWAY](https://themindzone.pages.dev/superwings-subway.html)
- [DINER IN THE STORM](https://themindzone.pages.dev/diner-in-the-storm.html)
- [FIND THE FROG HIDDEN OBJECTS](https://themindzone.pages.dev/find-the-frog-hidden-objects.html)
- [PUZZLE MASTERS TRAVELERS](https://learnquester.pages.dev/puzzle-masters-travelers.html)
- [CUTE CATS ADVENTURES](https://themindzone.pages.dev/cute-cats-adventures.html)
- [FIND THE MISSING PART](https://thelearnquester.web.app/find-the-missing-part.html)
- [GUNS VS MAGIC](https://thelearnquester.web.app/guns-vs-magic.html)
- [INDEX13](https://learnquesters.pages.dev/index13.html)
- [FASHIONISTA CHRISTMAS EVE PARTY](https://themindzone.pages.dev/fashionista-christmas-eve-party.html)
- [KINGDOM WARS TD](https://themindzone.pages.dev/kingdom-wars-td.html)
- [BANANA BOUNCE](https://themindzone.pages.dev/banana-bounce.html)
- [HORROR MINECRAFT PARTYTIME](https://themindzone.pages.dev/horror-minecraft-partytime.html)
- [MMA SUPER FIGHT](https://themindzone.pages.dev/mma-super-fight.html)
- [GOAL RUSH](https://themindzone.pages.dev/goal-rush.html)
- [SKATING PARK](https://iskillquest.pages.dev/skating-park.html)
- [SANDWICH RUNNER](https://themindzone.pages.dev/sandwich-runner.html)
- [ELEMENTAL DRESSUP MAGIC](https://themindzone.pages.dev/elemental-dressup-magic.html)
- [BRAIN FIND CAN YOU FIND IT](https://themindzone.pages.dev/brain-find-can-you-find-it.html)
- [SPRUNKI JIGSAW PUZZLE](https://thequizzone.pages.dev/sprunki-jigsaw-puzzle.html)
- [HOARD MASTER](https://thelearnquester.web.app/hoard-master.html)
- [MATCH MASTER](https://themindplay.github.io/match-master.html)
- [CATEGORY BYEPASSHUB](https://learnquester.pages.dev/category-byepasshub.html)
- [IDLE BATHROOM EMPIRE TYCOON](https://thelearnquesters.pages.dev/idle-bathroom-empire-tycoon.html)
- [ITALIAN BRAINROT JIGSAW](https://themindzone.pages.dev/italian-brainrot-jigsaw.html)
- [CATEGORY CASUAL 2](https://iskillquest.pages.dev/category-casual-2.html)
- [CATEGORY ART](https://learnquester.pages.dev/category-art.html)
- [PET CONNECT MATCH](https://learnquester.pages.dev/pet-connect-match.html)
- [UNDERWATER SURVIVAL DEEP DIVE](https://theskillquest.pages.dev/underwater-survival-deep-dive.html)
- [BFFS Y2K FASHION](https://learnquester.pages.dev/bffs-y2k-fashion.html)
- [MOJICON FRUIT CONNECT](https://thequizzone.pages.dev/mojicon-fruit-connect.html)
- [CATEGORY BOARDGAMES](https://learnquester.pages.dev/category-boardgames.html)
- [CATEGORY BRAIN260](https://learnquester.pages.dev/category-brain260.html)
- [CRIME THEFT GANGSTER PARADISE](https://thequizzone.pages.dev/crime-theft-gangster-paradise.html)
- [BLOCK PUZZLE JEWEL FOREST](https://learnquester.pages.dev/block-puzzle-jewel-forest.html)
- [CATEGORY ANIMAL216](https://thequizzone.pages.dev/category-animal216.html)
- [DONT PANIC DUDE](https://iskillquest.pages.dev/dont-panic-dude.html)
- [COWBOYS DUEL](https://thelearnquesters.pages.dev/cowboys-duel.html)
- [DOGE MATCH](https://thequizzone.pages.dev/doge-match.html)
- [PEG SOLITAIRE](https://learnquester.pages.dev/peg-solitaire.html)
- [INDEX2](https://thequizzone.pages.dev/index2.html)
- [ROYAL CROWN BLAST](https://thequizzone.pages.dev/royal-crown-blast.html)
- [TRAIN MASTER](https://themindzone.pages.dev/train-master.html)
- [BLOXORZ BLOCK PUZZLE 3D](https://iskillquest.pages.dev/bloxorz-block-puzzle-3d.html)
- [PUZZLEJAM](https://iskillquest.pages.dev/puzzlejam.html)
- [DRUNK BUT NOT WASTED KNIGHT](https://iskillquest.pages.dev/drunk-but-not-wasted-knight.html)
- [AIR BLOCK](https://learnquester.pages.dev/air-block.html)
- [GRAND MAHJONG CONNECT](https://themindzone.pages.dev/grand-mahjong-connect.html)
- [CLEAN THE OCEAN](https://iskillquest.pages.dev/clean-the-ocean.html)
- [CAR COLLISION MASTER](https://thequizzone.pages.dev/car-collision-master.html)
- [FARM BLOCK PUZZLE](https://themindzone.pages.dev/farm-block-puzzle.html)
- [KITTY SQUAD WINTER DRESS UP](https://learnquester.pages.dev/kitty-squad-winter-dress-up.html)
- [FUN TOWN PARKING](https://iskillquest.pages.dev/fun-town-parking.html)
- [CATEGORY BRAIN261](https://learnquester.pages.dev/category-brain261.html)
- [LINGO DREAMS](https://thelearnquester.web.app/lingo-dreams.html)
- [SERIOUS HEAD](https://themindzone.pages.dev/serious-head.html)
- [WORLD FLAGS TRIVIA](https://iskillquest.pages.dev/world-flags-trivia.html)
- [PLANET EVOLUTION IDLE CLICKER](https://thequizzone.pages.dev/planet-evolution-idle-clicker.html)
- [ESCAPE FROM THE PORTAL](https://thelearnquester.web.app/escape-from-the-portal.html)
- [REAL FLIGHT SIMULATOR](https://thelearnquesters.pages.dev/real-flight-simulator.html)
- [SAVE BABY CAPYBARAS PULL PIN](https://thelearnquesters.pages.dev/save-baby-capybaras-pull-pin.html)
- [FALLING MAN](https://thequizzone.pages.dev/falling-man.html)
- [DESERT ROVER SURVIVAL](https://learnquester.pages.dev/desert-rover-survival.html)
- [PYRAMIDZ](https://themindzone.pages.dev/pyramidz.html)
- [TOILET PIN](https://thequizzone.pages.dev/toilet-pin.html)
- [EMOJI GUESS](https://themindzone.pages.dev/emoji-guess.html)
- [DRAW CLIMB RACE THE ULTIMATE HILL CLIMBING CHALLENGE](https://iskillquest.pages.dev/draw-climb-race-the-ultimate-hill-climbing-challenge.html)
- [OBBY YARD SALE](https://thequizzone.pages.dev/obby-yard-sale.html)
- [HIGH HEELS 2](https://thequizzone.pages.dev/high-heels-2.html)
- [BUBBLE POP FAIRYLAND](https://iskillquest.pages.dev/bubble-pop-fairyland.html)
- [BUILD A QUEEN 2025](https://thelearnquesters.pages.dev/build-a-queen-2025.html)
- [INDEX4](https://thequizzone.pages.dev/index4.html)
- [TWO CARTS DOWNHILL](https://thequizzone.pages.dev/two-carts-downhill.html)
- [IDLE TRADE ROUTES](https://learnquester.pages.dev/idle-trade-routes.html)
- [MONSTERELLA FANTASY MAKEUP](https://themindzone.pages.dev/monsterella-fantasy-makeup.html)
- [SPRUNKI 3D ESCAPE](https://thelearnquesters.pages.dev/sprunki-3d-escape.html)
- [BLOCKY ARCHER RUN](https://thequizzone.pages.dev/blocky-archer-run.html)
- [PRINCESS ROYAL WEDDING](https://iskillquest.pages.dev/princess-royal-wedding.html)
- [FRUIT PARTY](https://thelearnquester.web.app/fruit-party.html)
- [HERO STORY MONSTERS CROSSING](https://iskillquest.pages.dev/hero-story-monsters-crossing.html)
- [INDEX25](https://thequizzone.pages.dev/index25.html)
- [FUN GOLF](https://learnquester.pages.dev/fun-golf.html)
- [PALM ISLAND SOLITAIRE](https://iskillquest.pages.dev/palm-island-solitaire.html)
- [MOW IT](https://learnquester.pages.dev/mow-it.html)
- [BLACK PINK HALLOWEEN CONCERT](https://themindzone.pages.dev/black-pink-halloween-concert.html)
- [SPRUNKI QUIZ](https://thelearnquester.web.app/sprunki-quiz.html)
- [WOOD SCREW PUZZLE](https://iskillquest.pages.dev/wood-screw-puzzle.html)
- [INDEX11](https://thequizzone.pages.dev/index11.html)
- [CS COMMAND SNIPERS](https://iskillquest.pages.dev/cs-command-snipers.html)
- [SLOPE SNOWBALL](https://thequizzone.pages.dev/slope-snowball.html)
- [BASKETBALL FEVER](https://thelearnquesters.pages.dev/basketball-fever.html)
- [MAKE TWO](https://learnquester.pages.dev/make-two.html)
- [BRAIN PUZZLES QUESTS](https://themindzone.pages.dev/brain-puzzles-quests.html)
- [IDLE BARBER SHOP](https://iskillquest.pages.dev/idle-barber-shop.html)
- [COLOR SCREW RESCUE PUZZLE](https://themindzone.pages.dev/color-screw-rescue-puzzle.html)
- [SNAKE PUZZLE SLITHER TO EAT](https://theskillquest.pages.dev/snake-puzzle-slither-to-eat.html)
- [CARS VS ZOMBIES](https://iskillquest.pages.dev/cars-vs-zombies.html)
- [CATEGORY CASUAL 2](https://learnquester.pages.dev/category-casual-2.html)
- [RACING GAME KING HP](https://thelearnquester.web.app/racing-game-king-hp.html)
- [DINO GAME](https://theskillquest.pages.dev/dino-game.html)
- [CATEGORY AGILITY 2](https://thequizzone.pages.dev/category-agility-2.html)
- [IDLE RESTAURANT TYCOON](https://thequizzone.pages.dev/idle-restaurant-tycoon.html)
- [AUTHENTIC FOOTBALL](https://learnquester.pages.dev/authentic-football.html)
- [MOW IT](https://thequizzone.pages.dev/mow-it.html)
- [ZOMBIE DERBY PIXEL SURVIVAL](https://theskillquest.pages.dev/zombie-derby-pixel-survival.html)
- [CATEGORY IDLE](https://themindplay.github.io/category-idle.html)
- [MAGIC KINGDOM HEX MATCH](https://iskillquest.pages.dev/magic-kingdom-hex-match.html)
