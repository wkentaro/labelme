# flake8: noqa

import logging
import pkg_resources


__appname__ = 'labelme'
__version__ = pkg_resources.get_distribution(__appname__).version

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__appname__)


from labelme import testing
from labelme import utils
