# flake8: noqa

import logging


__appname__ = 'labelme'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__appname__)


from labelme._version import __version__

from labelme import testing
from labelme import utils
