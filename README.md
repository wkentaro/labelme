# Dan's random labelme fork

## What am I using labelme for?

I am fine-tuning detector models that *almost* work in the target domain, but not quite.  In particular, I'm fine-tuning [MegaDetector](https://github.com/agentmorris/MegaDetector/) (MD) for cases where it [struggles](https://github.com/agentmorris/MegaDetector/blob/main/megadetector-challenges.md), but still has some signal.  In these cases, if you use MD to generate boxes, you will get many target objects and save yourself *gobs* of time in building a training set, but you will miss some target objects entirely, and you will have to use a sufficiently low confidence threshold that you get a bunch of junk.  Before I do any labelme work, I do an aggressive [repeat detection elimination](https://github.com/agentmorris/MegaDetector/tree/main/api/batch_processing/postprocessing/repeat_detection_elimination) pass, but still, there's some junk, and some misses, but mostly good boxes, and I want to clean all that up to make a new training set.

I compared a few OSS labeling tools and found that none *quite* supported this scenario, since the common path is still the one where you're making boxes from scratch.  But labelme was the easiest to populate with bounding boxes from ML results, and by far the easiest for me to modify (all in Python, no fancy-schmancy Web infrastructure).


## Why did I fork labelme?

I wanted to add a few UI features specific to the scenario where boxes are prepopulated from detector-generated boxes, to generate data I could use to train new detectors.  This scenario has a few unique UI requirements:

* Deleting boxes efficiently (i.e., without using the mouse) is more important than in the typical de-novo-boxes scenario
* Being able to definitively mark images as empty is important
* Fine adjustment of close-but-not-quite-there boxes (with the keyboard) is important
* Being able to page quickly through mostly-correct boxes and see huge bright red boxes that require almost no cognitive processing time is important

## Changes in this fork

* Shift/ctrl + up/down/left right move the upper-left and lower-right borders of a selected
  rectangle.

* The save action is enabled by default (so we can save images with no boxes)

* Shortcut to copy the current file to the clipboard (useful for re-starting where you left off when you've prepopulated the list, so the checkboxes aren't useuful)

* Allow saving annotations to the output_dir when output_dir is specified (I don't really remember why I did this) 

* Keyboard shortcut to select all polygons

* Command-line argument to resume from the last image you saved

* Customizable line width, including a command line option --linewidth

* Changes to the defaults that make it faster for cases where you're mostly just confirming boxes: a brighter color for the "animal" class, auto-save by default, don't save image binary data to .json by default

* Alt-right and alt-left to select next/prev boxes (super-useful for the case where multiple overlapping boxes are predicted for a single object, which is a time-consuming situation to resolve with the mouse)

## TODO

* My fine adjustment logic breaks down a little when boxes are near the edge of the canvas (nothing bad happens, fine adjustment just stops working), fix this

* Right now I do a one-time conversion of ML output to labelme files, and I choose a confidence threshold when doing that conversion.  I really really really want a way of quickly showing all the boxes below some backup confidence threshold, e.g. "press F1 to show (or load, but preferably just show) lower-confidence detections".  This would support the case where an object of interest missed the confidence threshold; in this case, I would load all the low-confidence detections, select all, unselect the object of interest, and delete the selected boxes, all without touching the mouse.

## Notes to self about how I set up my environment

### Setting up this repo

```bash
cd ~/git
git clone https://github.com/agentmorris/labelme
cd labelme
mamba create -n labelme-git python=3.11 pip -y && mamba activate labelme-git && pip install -e .
```

### Running labelme in the context of bbox refinement

#### When starting with new label files for a folder_name

`python labelme folder_name --labels animal --last_updated_file ~/labelme-last-updated.txt`

#### When resuming

`python labelme folder_name --labels animal --last_updated_file ~/labelme-last-updated.txt --resume_from_last_update`

#### If the app hangs on startup

`labelme --reset-config`

#### Stuff I had to do to make it work in WSL

...because I got QT errors.

```bash
sudo apt-get upgrade -y
sudo apt install -y libgl1-mesa-dev
# I don’t think this was necessary
export QT_QPA_PLATFORM="xcb"
sudo apt install libxcb-xinerama0 libqt5x11extras5
```

## Reminders of keyboard shortcuts I use

* A,D (previous/next)
* Ctrl-R (create rectangle mode)
* Ctrl-J (edit polygons mode)
* Ctrl-A (select all polygons)
* Alt-right/alt-left (select next/previous polygons)
* Shift/control + left/right/up/down (fine adjustment of 0th/1st vertices)
* Delete (delete current polygon)
* Ctrl-C,ctrl-v (copy/paste selected polygons)
