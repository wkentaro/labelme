# flake8: noqa

import logging
import sys

from qtpy import QT_VERSION


__appname__ = 'labelme'

QT4 = QT_VERSION[0] == '4'
QT5 = QT_VERSION[0] == '5'
del QT_VERSION

PY2 = sys.version[0] == '2'
PY3 = sys.version[0] == '3'
del sys


from labelme._version import __version__

from labelme import testing
from labelme import utils
