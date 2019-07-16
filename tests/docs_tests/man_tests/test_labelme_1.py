#!/usr/bin/env python

from __future__ import print_function

import os.path as osp
import re
import shlex
import subprocess
import sys


here = osp.dirname(osp.abspath(__file__))

cmd = 'help2man labelme'
man_expected = subprocess.check_output(shlex.split(cmd)).decode().splitlines()

with open(osp.join(here, '../../../docs/man/labelme.1')) as f:
    man_actual = f.read().splitlines()

patterns_exclude = [
    r'^\.TH .*',
    r'^config file.*',
]

FAIL = 0
for line_expected, line_actual in zip(man_expected, man_actual):
    for pattern in patterns_exclude:
        if re.match(pattern, line_expected) or re.match(pattern, line_actual):
            break
    else:
        if line_expected != line_actual:
            print(repr('> {}'.format(line_expected)), file=sys.stderr)
            print(repr('< {}'.format(line_actual)), file=sys.stderr)
            FAIL = 1

sys.exit(FAIL)
