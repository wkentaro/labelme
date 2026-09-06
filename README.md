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
- [BLOCK PUZZLE CATS](https://studyquesthub.web.app/block-puzzle-cats.html)
- [MOBILE PHONE CASE DESIGN DIY](https://thelearnquesters.pages.dev/mobile-phone-case-design-diy.html)
- [POPCORN STACK](https://studyplayings.pages.dev/popcorn-stack.html)
- [IMPOSTER 3D](https://studyplaying.github.io/imposter-3d.html)
- [WHEEL OF BINGO](https://studyplayings.web.app/wheel-of-bingo.html)
- [BRAIN FIND CAN YOU FIND IT](https://studyplayings.pages.dev/brain-find-can-you-find-it.html)
- [SORTSTORE](https://studyplaying.github.io/sortstore.html)
- [CATEGORY FOOD](https://quizverses.pages.dev/category-food.html)
- [MUSHROOM BLOCKS](https://studyplayings.web.app/mushroom-blocks.html)
- [STICKMAN DISMOUNT SIMULATOR](https://studyplaying.github.io/stickman-dismount-simulator.html)
- [CANASTA ROYALE OFFLINE](https://studyplaying.github.io/canasta-royale-offline.html)
- [CAT CHAOS SIMULATOR](https://quizverses.pages.dev/cat-chaos-simulator.html)
- [ELLIE S RECIPE DUBAI CHOCOLATE BAR](https://quizverses.pages.dev/ellie-s-recipe-dubai-chocolate-bar.html)
- [BLOCK BLAST JEWEL PUZZLE](https://studyquesthub.web.app/block-blast-jewel-puzzle.html)
- [ATHENA MATCH 2](https://studyquesthub.web.app/athena-match-2.html)
- [STOCKINGS DILEMMA](https://quizverses.pages.dev/stockings-dilemma.html)
- [CATEGORY RUNNING107](https://quizverses.pages.dev/category-running107.html)
- [TRIVIA NATION](https://studyplayings.web.app/trivia-nation.html)
- [CATEGORY AGILITY](https://studyplayings.pages.dev/category-agility.html)
- [CATEGORY CASUAL 7](https://quizverses.pages.dev/category-casual-7.html)
- [CLICKER HEROES](https://quizverses.pages.dev/clicker-heroes.html)
- [ICONIC HALLOWEEN COSTUMES](https://studyplaying.github.io/iconic-halloween-costumes.html)
- [HEAD RUNNER DASH](https://studyquesthub.web.app/head-runner-dash.html)
- [MURDER CASE CLUE 3D](https://quizverses.pages.dev/murder-case-clue-3d.html)
- [VALENTINES MAKEUP TRENDS](https://studyplaying.github.io/valentines-makeup-trends.html)
- [MALL ANOMALY](https://studyplaying.github.io/mall-anomaly.html)
- [CHICKEN BANANA RUN](https://studyquests.pages.dev/chicken-banana-run.html)
- [PARKOUR BLOCK 6](https://studyplayings.web.app/parkour-block-6.html)
- [CATEGORY SOCCER](https://quizverses.pages.dev/category-soccer.html)
- [SURVEV](https://studyquesthub.web.app/survev.html)
- [SWORD RUN 3D](https://studyplaying.github.io/sword-run-3d.html)
- [TINY FARM](https://quizverses.pages.dev/tiny-farm.html)
- [GHOST ESCAPE 3D](https://studyplayings.web.app/ghost-escape-3d.html)
- [CLOAK MASTER SHOOTER RUN](https://studyplaying.github.io/cloak-master-shooter-run.html)
- [HIDE ME](https://studyquesthub.web.app/hide-me.html)
- [STICKMAN FIGHT PRO](https://studyplaying.github.io/stickman-fight-pro.html)
- [SHANGHAI CHEF](https://quizverses.pages.dev/shanghai-chef.html)
- [CATEGORY MOBILE2 112](https://quizverses.pages.dev/category-mobile2-112.html)
- [OVERFLOWING PALETTE](https://studyplayings.web.app/overflowing-palette.html)
- [ART PUZZLE MASTER](https://studyquesthub.web.app/art-puzzle-master.html)
- [CATEGORY MAKEUP CATEGORY](https://quizverses.pages.dev/category-makeup-category.html)
- [TWO STUNT SUPERCARS](https://quizverses.pages.dev/two-stunt-supercars.html)
- [JOURNEY OF ESCAPE](https://studyplaying.github.io/journey-of-escape.html)
- [MERGE 2048 CAKE](https://quizverses.pages.dev/merge-2048-cake.html)
- [LIVE 100 DAYS](https://studyquests.pages.dev/live-100-days.html)
- [COLOR MIX JELLY MERGE](https://studyplayings.web.app/color-mix-jelly-merge.html)
- [CATEGORY HORROR 2](https://quizverses.pages.dev/category-horror-2.html)
- [OFFROAD JEEP GAME SIMULATOR](https://studyplaying.github.io/offroad-jeep-game-simulator.html)
- [CHALLENGER CITY DRIVER](https://studyplayings.web.app/challenger-city-driver.html)
- [CATEGORY UNBLOCKED WEBSITE](https://quizverses.pages.dev/category-unblocked-website.html)
- [HOTGEAR](https://studyplaying.github.io/hotgear.html)
- [BUILDING MODS FOR MINECRAFT](https://studyplaying.github.io/building-mods-for-minecraft.html)
- [TOILET TIME](https://studyplaying.github.io/toilet-time.html)
- [DARK STONES CARD BATTLE RPG](https://studyplaying.github.io/dark-stones-card-battle-rpg.html)
- [JENNYS MATH PUZZLE](https://studyquesthub.web.app/jennys-math-puzzle.html)
- [NITRO SPEED CAR RACING](https://studyplaying.github.io/nitro-speed-car-racing.html)
- [SERIOUS HEAD](https://studyplaying.github.io/serious-head.html)
- [FEED THE PARROT](https://studyplaying.github.io/feed-the-parrot.html)
- [FOREST TILES](https://studyplaying.github.io/forest-tiles.html)
- [SOLITAIRE KLONDIKE TREASURE ISLAND](https://quizverses.pages.dev/solitaire-klondike-treasure-island.html)
- [CAPYBARA SUIKA](https://quizverses.pages.dev/capybara-suika.html)
- [ROLLING BALLS SEA RACE](https://studyquesthub.web.app/rolling-balls-sea-race.html)
- [AVATAR LIFE MY TOWN](https://studyplaying.github.io/avatar-life-my-town.html)
- [SNOWFLIGHT](https://studyplayings.web.app/snowflight.html)
- [KINGDOM MATCH](https://studyquests.pages.dev/kingdom-match.html)
- [WORD OF FORTUNE](https://studyplaying.github.io/word-of-fortune.html)
- [CATEGORY EDUCATIONAL25](https://studyplaying.github.io/category-educational25.html)
- [GEOMETRY STARS](https://quizverses.pages.dev/geometry-stars.html)
- [CATEGORY QUIZ](https://studyplayings.web.app/category-quiz.html)
- [RED STICKMAN VS CRAFTMANS](https://studyquesthub.web.app/red-stickman-vs-craftmans.html)
- [GOBATTLEIO](https://studyplaying.github.io/gobattleio.html)
- [INDEX29](https://studyplaying.github.io/index29.html)
- [CRIME THEFT GANGSTER PARADISE](https://studyplaying.github.io/crime-theft-gangster-paradise.html)
- [ARCADE ROPE](https://studyplayings.pages.dev/arcade-rope.html)
- [KICK THE NOOBIK 3D](https://studyplayings.web.app/kick-the-noobik-3d.html)
- [FRUIT MERGE JUICY DROP GAME](https://studyquests.pages.dev/fruit-merge-juicy-drop-game.html)
- [HIGH SPEED CRAZY BIKE](https://studyplayings.web.app/high-speed-crazy-bike.html)
- [FRUIT KING MERGE](https://quizverses.pages.dev/fruit-king-merge.html)
- [CUPID UNCHAINED](https://studyplayings.web.app/cupid-unchained.html)
- [CATEGORY CASUAL969](https://quizverses.pages.dev/category-casual969.html)
- [HIDDEN OBJECT MY HOTEL](https://quizverses.pages.dev/hidden-object-my-hotel.html)
- [STICKMAN FOOTBALL](https://quizverses-9d2f2.web.app/stickman-football.html)
- [FRUIT BLOCK TETRA PUZZLE](https://studyquests.pages.dev/fruit-block-tetra-puzzle.html)
- [TIC TAC TOE MATCH THREE](https://studyplayings.web.app/tic-tac-toe-match-three.html)
- [FIGHT TO THE END](https://quizverses.pages.dev/fight-to-the-end.html)
- [XMAS HEXA SORT](https://studyquests.pages.dev/xmas-hexa-sort.html)
- [SKIBRONX RUNNER](https://studyquests.pages.dev/skibronx-runner.html)
- [ROYAL GARDEN MATCH 2](https://studyplayings.web.app/royal-garden-match-2.html)
- [RAGDOLL MEGA DUNK](https://studyquests.pages.dev/ragdoll-mega-dunk.html)
- [CATEGORY PLATFORM260](https://quizverses-9d2f2.web.app/category-platform260.html)
- [CATEGORY BALL173](https://studyplayings.web.app/category-ball173.html)
- [IDLE PET](https://studyquests.pages.dev/idle-pet.html)
- [SMART DOTS RELOADED](https://quizverses.pages.dev/smart-dots-reloaded.html)
- [AIRPORT SECURITY](https://quizverses.pages.dev/airport-security.html)
- [COLORSFORMS](https://studyplaying.github.io/colorsforms.html)
- [DOGE MATCH](https://quizverses-9d2f2.web.app/doge-match.html)
- [FISHING THE RUSSIAN WAY](https://studyplaying.github.io/fishing-the-russian-way.html)
- [EAT AND GROW FISH](https://studyquesthub.web.app/eat-and-grow-fish.html)
- [BITGOBLINS RPG SIMULATOR](https://studyquests.pages.dev/bitgoblins-rpg-simulator.html)
- [WORLD WAR 2 SHOOTER](https://studyplaying.github.io/world-war-2-shooter.html)
- [MUSIC CAT PIANO TILES GAME 3D](https://studyplaying.github.io/music-cat-piano-tiles-game-3d.html)
- [POTTERY MASTER](https://studyplaying.github.io/pottery-master.html)
- [ONLINE PORTAL](https://studyplayings.web.app/)
- [KILLER ESCAPE HUGGY EXTREME](https://learnquester.github.io/killer-escape-huggy-extreme.html)
- [CATEGORY ESCAPE187](https://thelearnquester.web.app/category-escape187.html)
- [MAZE CRAZE](https://thelearnquester.web.app/maze-craze.html)
- [PAWS OFF MY CLUES](https://quizverses.pages.dev/paws-off-my-clues.html)
- [WORM ESCAPE](https://studyquesthub.web.app/worm-escape.html)
- [SPRUNKI QUIZ](https://studyplayings.web.app/sprunki-quiz.html)
- [DINO SHOOTER PRO](https://quizverses.github.io/dino-shooter-pro.html)
- [VEGAMIX2 WILD WEST](https://studyquesthub.web.app/vegamix2-wild-west.html)
- [SCARY BABY YELLOW GAME](https://quizverses.pages.dev/scary-baby-yellow-game.html)
- [MINI GOLF BATTLE](https://studyplayings.web.app/mini-golf-battle.html)
- [CATEGORY CASUAL 6](https://quizverses-9d2f2.web.app/category-casual-6.html)
- [STRIKE BREAKOUT](https://learnquester.github.io/strike-breakout.html)
- [CAR PARKING SIMULATOR](https://quizverses.pages.dev/car-parking-simulator.html)
- [IDLE LUNCH](https://studyquests.pages.dev/idle-lunch.html)
- [DESIGN WITH ME SUPERHERO TUTU OUTFITS](https://studyquests.pages.dev/design-with-me-superhero-tutu-outfits.html)
- [CRAFT MAN VS GIANT TNT](https://quizverses.github.io/craft-man-vs-giant-tnt.html)
- [HIDDEN OBJECTS BAKERY](https://studyquests.pages.dev/hidden-objects-bakery.html)
- [TRAFFIC COP 3D](https://thelearnquester.web.app/traffic-cop-3d.html)
- [KINGDOM WARS TD](https://studyquesthub.web.app/kingdom-wars-td.html)
- [TILE HEX WORLD RED VS BLUE](https://studyquesthub.web.app/tile-hex-world-red-vs-blue.html)
- [CATEGORY FASHION105](https://quizverses-9d2f2.web.app/category-fashion105.html)
- [FIRESIDE SOLITAIRE](https://studyplaying.github.io/fireside-solitaire.html)
- [WRECK THE TOWER](https://studyquesthub.web.app/wreck-the-tower.html)
- [CARS MERGE](https://studyplayings.web.app/cars-merge.html)
- [CATEGORY GOGUARDIAN](https://quizverses.pages.dev/category-goguardian.html)
- [INDEX16](https://quizverses-9d2f2.web.app/index16.html)
- [OBBY 3D SPRUNKI PARKOUR](https://learnquester.pages.dev/obby-3d-sprunki-parkour.html)
