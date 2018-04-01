import base64
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
        self.filename = filename

    def load(self, filename):
        try:
            with open(filename, 'rb' if PY2 else 'r') as f:
                data = json.load(f)
                if data['imageData'] is not None:
                    imageData = base64.b64decode(data['imageData'])
                else:
                    # relative path from label file to relative path from cwd
                    imagePath = os.path.join(os.path.dirname(filename),
                                             data['imagePath'])
                    with open(imagePath, 'rb') as f:
                        imageData = f.read()
                lineColor = data['lineColor']
                fillColor = data['fillColor']
                shapes = (
                    (s['label'], s['points'], s['line_color'], s['fill_color'])
                    for s in data['shapes']
                )
                # Only replace data after everything is loaded.
                self.shapes = shapes
                self.imagePath = data['imagePath']
                self.imageData = imageData
                self.lineColor = lineColor
                self.fillColor = fillColor
                self.filename = filename
        except Exception as e:
            raise LabelFileError(e)

    def save(self, filename, shapes, imagePath, imageData=None,
             lineColor=None, fillColor=None):
        if imageData is not None:
            imageData = base64.b64encode(imageData).decode('utf-8')
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
            self.filename = filename
        except Exception as e:
            raise LabelFileError(e)

    @staticmethod
    def isLabelFile(filename):
        return os.path.splitext(filename)[1].lower() == LabelFile.suffix
