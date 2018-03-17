#
# Copyright (C) 2011 Michael Pitidis, Hussein Abdulwahid.
#
# This file is part of Labelme.
#
# Labelme is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Labelme is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Labelme.  If not, see <http://www.gnu.org/licenses/>.
#

from base64 import b64encode, b64decode
import json
import os.path
import sys


PY2 = sys.version_info[0] == 2


class LabelFileError(Exception):
    pass

class LabelFile(object):
    suffix = '.json'

    def __init__(self, filename=None):
        self.shapes = ()
        self.imagePath = None
        self.imageData = None
        if filename is not None:
            self.load(filename)

    def load(self, filename):
        try:
            with open(filename, 'rb' if PY2 else 'r') as f:
                data = json.load(f)
                imagePath = data['imagePath']
                if data['imageData'] is not None:
                    imageData = b64decode(data['imageData'])
                else:
                    imagePath = os.path.join(
                        os.path.dirname(filename), data['imagePath'])
                    with open(imagePath, 'rb') as f:
                        imageData = f.read()
                lineColor = data['lineColor']
                fillColor = data['fillColor']
                shapes = ((s['label'], s['points'], s['line_color'], s['fill_color'])\
                        for s in data['shapes'])
                # Only replace data after everything is loaded.
                self.shapes = shapes
                self.imagePath = imagePath
                self.imageData = imageData
                self.lineColor = lineColor
                self.fillColor = fillColor
        except Exception as e:
            raise LabelFileError(e)

    def save(self, filename, shapes, imagePath, imageData=None,
            lineColor=None, fillColor=None):
        if imageData is not None:
            imageData = b64encode(imageData).decode('utf-8')
        data = dict(
            shapes=shapes,
            lineColor=lineColor,
            fillColor=fillColor,
            imagePath=imagePath,
            imageData=imageData,
        )
        try:
            with open(filename, 'wb' if PY2 else 'w') as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
        except Exception as e:
            raise LabelFileError(e)

    @staticmethod
    def isLabelFile(filename):
        return os.path.splitext(filename)[1].lower() == LabelFile.suffix
