labelme: Image Annotation Tool with Python
==========================================

Labelme is a graphical image annotation tool inspired by
http://labelme.csail.mit.edu.

It is written in Python and uses Qt for its graphical interface.


Dependencies
------------

-  `PyQt4 <http://www.riverbankcomputing.co.uk/software/pyqt/intro>`_


Installation
------------

On Ubuntu:

.. code-block:: bash

  $ sudo apt-get install python-qt4 qt4-dev-tools

  $ sudo pip install labelme


On OS X:

.. code-block:: bash

  $ brew install qt qt4

  $ pip install labelme


Usage
-----

.. code:: bash

  $ labelme  # Open GUI

At the moment annotations are saved as a `JSON <http://www.json.org/>`_
file. The file includes the image itself. In the feature support for XML
output or possibly even `SVG <http://www.w3.org/Graphics/SVG/>`_ will
be added.


Screencast
----------

.. figure:: https://github.com/wkentaro/labelme/raw/master/_media/screencast.gif
   :width: 80%
