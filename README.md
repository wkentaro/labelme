## Why did I fork labelme?

I just wanted to add a few UI features specific to the scenario where boxes are prepopulated from detector-generated boxes, to generate data I could use to train new detectors.  This means that (a) deleting boxes is important, (b) being able to definitively mark images as empty is important, and (c) fine adjustment of close-but-not-quite-there boxes (with the keyboard) is important.


## Changes in this fork

* Shift/ctrl + up/down/left right move the upper-left and lower-right borders of a selected
  rectangle.

* The save action is enabled by default (so we can save images with no boxes)

* Shortcut to copy the current file to the clipboard (useful for re-starting where you left off when you've prepopulated the list, so the checkboxes aren't useuful)

* Allow saving annotations to the output_dir when output_dir is specified (I don't really remember why I did this) 

* Keyboard shortcut to select all polygons

