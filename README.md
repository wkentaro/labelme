labelme: Image Annotation Tool with Python
==========================================

[![PyPI Version](https://img.shields.io/pypi/v/labelme.svg)](https://pypi.python.org/pypi/labelme)
[![Travis Build Status](https://travis-ci.org/wkentaro/labelme.svg?branch=master)](https://travis-ci.org/wkentaro/labelme)
[![Appveyor Build status](https://ci.appveyor.com/api/projects/status/epxf9b6c47cw373y/branch/master?svg=true)](https://ci.appveyor.com/project/wkentaro/labelme/branch/master)
[![Docker Build Status](https://img.shields.io/docker/build/wkentaro/labelme.svg)](https://hub.docker.com/r/wkentaro/labelme)


Labelme is a graphical image annotation tool inspired by <http://labelme.csail.mit.edu>.

It is written in Python and uses Qt for its graphical interface.


Dependencies
------------

- [PyQt4 or PyQt5](http://www.riverbankcomputing.co.uk/software/pyqt/intro)


Installation
------------

There are options:

- Platform agonistic installation: Anaconda, Docker
- Platform specific installation: Ubuntu, macOS

**Anaconda**

You need install [Anaconda](https://www.continuum.io/downloads), then run below:

```bash
conda create --name=labelme python=2.7
source activate labelme
conda install pyqt
pip install labelme
```

**Docker**

You need install [docker](https://www.docker.com), then run below:

```bash
wget https://raw.githubusercontent.com/wkentaro/labelme/master/scripts/labelme_on_docker
chmod u+x labelme_on_docker

# Maybe you need http://sourabhbajaj.com/blog/2017/02/07/gui-applications-docker-mac/ on macOS
./labelme_on_docker static/apc2016_obj3.jpg -O static/apc2016_obj3.json
```

**Ubuntu**

```bash
sudo apt-get install python-qt4 pyqt4-dev-tools
sudo pip install labelme
```

**macOS**

```bash
brew install qt qt4 || brew install pyqt  # qt4 is deprecated
pip install labelme
```


Usage
-----

**Annotation**

Run `labelme --help` for detail.

```bash
labelme  # Open GUI
labelme static/apc2016_obj3.jpg  # Specify file
labelme static/apc2016_obj3.jpg -O static/apc2016_obj3.json  # Close window after the save
```

The annotations are saved as a [JSON](http://www.json.org/) file. The
file includes the image itself.

**Visualization**

To view the json file quickly, you can use utility script:

```bash
labelme_draw_json static/apc2016_obj3.json
```

**Convert to Dataset**

To convert the json to set of image and label, you can run following:


```bash
labelme_json_to_dataset static/apc2016_obj3.json
```


Sample
------

- [Original Image](https://github.com/wkentaro/labelme/blob/master/static/apc2016_obj3.jpg)
- [Screenshot](https://github.com/wkentaro/labelme/blob/master/static/apc2016_obj3_screenshot.jpg)
- [Generated Json File](https://github.com/wkentaro/labelme/blob/master/static/apc2016_obj3.json)
- [Visualized Json File](https://github.com/wkentaro/labelme/blob/master/static/apc2016_obj3_draw_json.jpg)


Screencast
----------

<img src="https://github.com/wkentaro/labelme/raw/master/static/screencast.gif" width="70%"/>
