# flake8: noqa

import logging
import sys

from qtpy import QT_VERSION


__appname__ = "labelme"

# Semantic Versioning 2.0.0: https://semver.org/
# 1. MAJOR version when you make incompatible API changes;
# 2. MINOR version when you add functionality in a backwards-compatible manner;
# 3. PATCH version when you make backwards-compatible bug fixes.
# 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta
# < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0. == 1.0.0+1
__version__ = "5.2.0+1"

QT4 = QT_VERSION[0] == "4"
QT5 = QT_VERSION[0] == "5"
del QT_VERSION

PY2 = sys.version[0] == "2"
PY3 = sys.version[0] == "3"
del sys

from labelme.label_file import LabelFile
from labelme import testing
from labelme import utils
