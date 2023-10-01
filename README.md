## What am I using labelme for?

I am fine-tuning detector models that *almost* work in the target domain, but not quite.  In particular, I'm fine-tuning [MegaDetector](https://github.com/agentmorris/MegaDetector/) (MD) for cases where it [struggles](https://github.com/agentmorris/MegaDetector/blob/main/megadetector-challenges.md), but still has some signal.  In these cases, if you use MD to generate boxes, you will get many target objects and save yourself *gobs* of time in building a training set, but you will miss some target objects entirely, and you will have to use a sufficiently low confidence threshold that you get a bunch of junk.  Before I do any labelme work, I do an aggressive [repeat detection elimination](https://github.com/agentmorris/MegaDetector/tree/main/api/batch_processing/postprocessing/repeat_detection_elimination) pass, but still, there's some junk, and some misses, but mostly good boxes, and I want to clean all that up to make a new training set.

I compared a few OSS labeling tools and found that none *quite* supported this scenario, since the common path is still the one where you're making boxes from scratch.  But labelme was the easiest to populate with bounding boxes from ML results, and by far the easiest for me to modify (all in Python, no fancy-schmancy Web infrastructure).


## Why did I fork labelme?

I wanted to add a few UI features specific to the scenario where boxes are prepopulated from detector-generated boxes, to generate data I could use to train new detectors.  This scenario has a few unique UI requirements:

* Deleting boxes efficient (i.e., without using the mouse) is more important than in the typical de-novo-boxes scenario
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

