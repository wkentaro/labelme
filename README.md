labelme: Image Annotation Tool with Python
==========================================

Labelme is a graphical image annotation tool inspired by <http://labelme.csail.mit.edu>.

It is written in Python and uses Qt for its graphical interface.


Dependencies
------------

- [PyQt4](http://www.riverbankcomputing.co.uk/software/pyqt/intro)


Installation
------------

On Ubuntu:

```bash
$ sudo apt-get install python-qt4 qt4-dev-tools

$ sudo pip install labelme
```

On OS X:

```bash
$ brew install qt qt4

$ pip install labelme
```


Usage
-----

```bash
$ labelme  # Open GUI
```

The annotations are saved as a [JSON](http://www.json.org/) file. The
file includes the image itself.

To view the json file quickly, you can use utility script:

```bash
$ labelme_draw_json sample.json
```


Sample
------

- [Original Image](https://github.com/wkentaro/labelme/blob/master/_media/IMG_6319.jpg)
- [Screenshot](https://github.com/wkentaro/labelme/blob/master/_media/IMG_6319_screenshot.png)
- [Generated Json File](https://github.com/wkentaro/labelme/blob/master/_media/IMG_6319.json)
- [Visualized Json File](https://github.com/wkentaro/labelme/blob/master/_media/IMG_6319_draw_json.png)


Screencast
----------

<img src="https://github.com/wkentaro/labelme/raw/master/_media/screencast.gif" width="70%"/>
