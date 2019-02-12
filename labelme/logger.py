import logging

import termcolor

from . import __appname__


COLORS = {
    'WARNING': 'yellow',
    'INFO': 'white',
    'DEBUG': 'blue',
    'CRITICAL': 'red',
    'ERROR': 'red',
}


class ColoredFormatter(logging.Formatter):

    def __init__(self, msg, use_color=True):
        logging.Formatter.__init__(self, msg)
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in COLORS:
            colored_levelname = termcolor.colored(
                '[{}]'.format(levelname), color=COLORS[levelname]
            )
            record.levelname = colored_levelname
        return logging.Formatter.format(self, record)


class ColoredLogger(logging.Logger):

    fmt_filename = termcolor.colored('%(filename)s', attrs={'bold': True})
    FORMAT = '%(levelname)s %(message)s ({}:%(lineno)d)'.format(fmt_filename)

    def __init__(self, name):
        logging.Logger.__init__(self, name, logging.INFO)

        color_formatter = ColoredFormatter(self.FORMAT)

        console = logging.StreamHandler()
        console.setFormatter(color_formatter)

        self.addHandler(console)
        return


logging.setLoggerClass(ColoredLogger)
logger = logging.getLogger(__appname__)
