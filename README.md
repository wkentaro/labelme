<img src="https://github.com/wkentaro/labelme/blob/master/labelme/icons/icon.png?raw=true" align="right" />

labelme: Image Polygonal Annotation with Python
===============================================

[![PyPI Version](https://img.shields.io/pypi/v/labelme.svg)](https://pypi.python.org/pypi/labelme)
[![Travis Build Status](https://travis-ci.org/wkentaro/labelme.svg?branch=master)](https://travis-ci.org/wkentaro/labelme)
[![Docker Build Status](https://img.shields.io/docker/build/wkentaro/labelme.svg)](https://hub.docker.com/r/wkentaro/labelme)


Labelme is a graphical image annotation tool inspired by <http://labelme.csail.mit.edu>.  
It is written in Python and uses Qt for its graphical interface.

<img src="examples/single_image/.readme/screenshot.jpg" width="80%" />


Requirements
------------

- Ubuntu / macOS / Windows
- Python2 / Python3
- [PyQt4 / PyQt5](http://www.riverbankcomputing.co.uk/software/pyqt/intro)


Installation
------------

There are options:

- Platform agonistic installation: Anaconda, Docker
- Platform specific installation: Ubuntu, macOS

**Anaconda**

You need install [Anaconda](https://www.continuum.io/downloads), then run below:

```bash
# python2
conda create --name=labelme python=2.7
source activate labelme
conda install pyqt
pip install labelme

# python3
conda create --name=labelme python=3.6
source activate labelme
# conda install pyqt
pip install pyqt5  # pyqt5 can be installed via pip on python3
pip install labelme
```

**Docker**

You need install [docker](https://www.docker.com), then run below:

```bash
wget https://raw.githubusercontent.com/wkentaro/labelme/master/scripts/labelme_on_docker
chmod u+x labelme_on_docker

# Maybe you need http://sourabhbajaj.com/blog/2017/02/07/gui-applications-docker-mac/ on macOS
labelme_on_docker examples/single_image/apc2016_obj3.jpg -O examples/single_image/apc2016_obj3.json
labelme_on_docker examples/semantic_segmentation/data_annotated
```

**Ubuntu**

```bash
# Ubuntu 14.04
sudo apt-get install python-qt4 pyqt4-dev-tools
sudo pip install labelme  # python2
sudo apt-get install python3-pyqt5 pyqt5-dev-tools
sudo pip3 install labelme  # python3

# Ubuntu 16.04
sudo apt-get install python-pyqt5 pyqt5-dev-tools
sudo pip install labelme  # python2
sudo apt-get install python3-pyqt5 pyqt5-dev-tools
sudo pip3 install labelme  # python3
```

**macOS**

```bash
# macOS Sierra
brew install pyqt  # maybe pyqt5
pip install labelme  # both python2/3 should work
```


Usage
-----

Run `labelme --help` for detail.  
The annotations are saved as a [JSON](http://www.json.org/) file.

```bash
labelme  # just open gui

# single image example
cd examples/single_image
labelme apc2016_obj3.jpg  # specify image file
labelme apc2016_obj3.jpg -O apc2016_obj3.json  # close window after the save
labelme apc2016_obj3.jpg --nodata  # not include image data but relative image path in JSON file
labelme apc2016_obj3.jpg \
  --labels highland_6539_self_stick_notes,mead_index_cards,kong_air_dog_squeakair_tennis_ball  # specify label list

# semantic segmentation example
cd examples/semantic_segmentation
labelme data_annotated/  # Open directory to annotate all images in it
labelme data_annotated/ --labels labels.txt  # specify label list with a file
```

For more advanced usage, please refer to the examples:

* [Single Image Example](examples/single_image)
* [Semantic Segmentation Example](examples/semantic_segmentation)
* [Instance Segmentation Example](examples/instance_segmentation)


Screencast
----------

<img src=".readme/screencast.gif" width="70%"/>


Acknowledgement
---------------

This repo is the fork of [mpitid/pylabelme](https://github.com/mpitid/pylabelme),
whose development has already stopped.
