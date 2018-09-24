# flake8: noqa

import logging
from qtpy import QT_VERSION


__appname__ = 'labelme'

QT5 = QT_VERSION[0] == '5'
del QT_VERSION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__appname__)


from labelme._version import __version__

from labelme import testing
from labelme import utils
