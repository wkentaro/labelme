import sys

from qtpy import QT_VERSION

__appname__ = "labelme"

# Semantic Versioning 2.0.0: https://semver.org/
# 1. MAJOR version when you make incompatible API changes;
# 2. MINOR version when you add functionality in a backwards-compatible manner;
# 3. PATCH version when you make backwards-compatible bug fixes.
# e.g., 1.0.0a0, 1.0.0a1, 1.0.0b0, 1.0.0rc0, 1.0.0, 1.0.0.post0
__version__ = "5.6.0a0"

QT4 = QT_VERSION[0] == "4"
QT5 = QT_VERSION[0] == "5"

PY2 = sys.version[0] == "2"
PY3 = sys.version[0] == "3"

# These need to be later than the above definitions due to
# circular import dependencies.

from labelme import testing
from labelme import utils
from labelme.label_file import LabelFile

__all__ = [
    "__appname__",
    "LabelFile",
    "PY2",
    "PY3",
    "QT4",
    "QT5",
    "testing",
    "utils",
]
