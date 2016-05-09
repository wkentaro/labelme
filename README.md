# labelme: Image Annotation Tool with Python

Labelme is a graphical image annotation tool inspired by
http://labelme.csail.mit.edu.

It is written in Python and uses Qt for its graphical interface.

## Dependencies

Labelme requires at least [Python 2.6](http://www.python.org/getit/) and
has been tested with [PyQt
4.8](http://www.riverbankcomputing.co.uk/software/pyqt/intro).

## Usage

After cloning the code you should first run `make` to generate the
resource file (a Python module containing all the icons).

You can then start annotating by running `./labelme.py`. For usage
instructions you can view the screencast tutorial from the `Help` menu.

At the moment annotations are saved as a [JSON](http://www.json.org/) file.
The file includes the image itself. In the feature support for XML
output or possibly even [SVG](http://www.w3.org/Graphics/SVG/) will be added.

## TODO

- Refactor into a Python package.
- Add installation script.
