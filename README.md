# labelme: Image Annotation Tool with Python

Labelme is a graphical image annotation tool inspired by
http://labelme.csail.mit.edu.

It is written in Python and uses Qt for its graphical interface.


## Dependencies

- [PyQt4](http://www.riverbankcomputing.co.uk/software/pyqt/intro)


## Usage


```bash
$ pip install labelme

$ labelme  # Open GUI
```

At the moment annotations are saved as a [JSON](http://www.json.org/) file.
The file includes the image itself. In the feature support for XML
output or possibly even [SVG](http://www.w3.org/Graphics/SVG/) will be added.
