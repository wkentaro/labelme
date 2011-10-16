
import json
import os.path

from base64 import b64encode, b64decode

class LabelFileError(Exception):
    pass

class LabelFile(object):
    suffix = '.lif'

    def __init__(self, filename=None):
        self.shapes = ()
        self.imagePath = None
        self.imageData = None
        if filename is not None:
            self.load(filename)

    def load(self, filename):
        try:
            with open(filename, 'rb') as f:
                data = json.load(f)
                imagePath = data['imagePath']
                imageData = b64decode(data['imageData'])
                shapes = ((s['label'], s['points']) for s in data['shapes'])
                # Only replace data after everything is loaded.
                self.shapes = shapes
                self.imagePath = imagePath
                self.imageData = imageData
        except Exception, e:
            raise LabelFileError(e)

    def save(self, filename, shapes, imagePath, imageData):
        try:
            with open(filename, 'wb') as f:
                json.dump(dict(
                    shapes=[dict(label=l, points=p) for (l, p) in shapes],
                    imagePath=imagePath,
                    imageData=b64encode(imageData)),
                    f, ensure_ascii=True, indent=2)
        except Exception, e:
            raise LabelFileError(e)

    @staticmethod
    def isLabelFile(filename):
        return os.path.splitext(filename)[1].lower() == LabelFile.suffix

