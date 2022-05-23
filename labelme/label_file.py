import base64
import contextlib
import io
import json
import os.path as osp

import PIL.Image

from labelme import __version__
from labelme.logger import logger
from labelme import PY2
from labelme import QT4
from labelme import utils


PIL.Image.MAX_IMAGE_PIXELS = None


@contextlib.contextmanager
def open(name, mode):
    assert mode in ["r", "w"]
    if PY2:
        mode += "b"
        encoding = None
    else:
        encoding = "utf-8"
    yield io.open(name, mode, encoding=encoding)
    return


class LabelFileError(Exception):
    pass


class LabelFile(object):

    suffix = ".json"

    def __init__(self, filename=None):
        self.shapes = []
        self.imagePath = None
        self.imageData = None
        if filename is not None:
            self.load(filename)
        self.filename = filename

    @staticmethod
    def load_image_file(filename):
        try:
            image_pil = PIL.Image.open(filename)
        except IOError:
            logger.error("Failed opening image file: {}".format(filename))
            return

        # apply orientation to image according to exif
        image_pil = utils.apply_exif_orientation(image_pil)

        with io.BytesIO() as f:
            ext = osp.splitext(filename)[1].lower()
            if PY2 and QT4:
                format = "PNG"
            elif ext in [".jpg", ".jpeg"]:
                format = "JPEG"
            else:
                format = "PNG"
            image_pil.save(f, format=format)
            f.seek(0)
            return f.read()

    def transform_deepwalk_labels(self, deepwalk_data):
        data = {
            "version": __version__,
            "imagePath": "",
            "imageData": None,
            "shapes": {},
            "flags": {},
            "imageHeight": None,
            "imageWidth": None
        }

        if "regions" in deepwalk_data and deepwalk_data["regions"] is not None:
            data["shapes"] = deepwalk_data["regions"]

        if "flags" in deepwalk_data and deepwalk_data["flags"] is not None:
            data["flags"] = deepwalk_data["flags"]

        if "color_filename" in deepwalk_data and deepwalk_data["color_filename"] is not None and deepwalk_data["color_filename"]:
            data["imagePath"] = deepwalk_data["color_filename"]

        return data
        

    def load(self, filename):
        keys = [
            "version",
            "imageData",
            "imagePath",
            "shapes",  # polygonal annotations
            "flags",  # image level flags
            "imageHeight",
            "imageWidth",
        ]
        shape_keys = [
            "label",
            "points",
            "group_id",
            "shape_type",
            "flags",
        ]
        try:
            with open(filename, "r") as f:
                deepwalk_data = json.load(f)

            data = self.transform_deepwalk_labels(deepwalk_data)

            version = data.get("version")
            if version is None:
                logger.warn(
                    "Loading JSON file ({}) of unknown version".format(
                        filename
                    )
                )
            elif version.split(".")[0] != __version__.split(".")[0]:
                logger.warn(
                    "This JSON file ({}) may be incompatible with "
                    "current labelme. version in file: {}, "
                    "current version: {}".format(
                        filename, version, __version__
                    )
                )

            if data["imageData"] is not None:
                imageData = base64.b64decode(data["imageData"])
                if PY2 and QT4:
                    imageData = utils.img_data_to_png_data(imageData)
            else:
                # relative path from label file to relative path from cwd
                imagePath = osp.join(osp.dirname(filename), data["imagePath"])
                imageData = self.load_image_file(imagePath)

            flags = data.get("flags") or {}
            imagePath = data["imagePath"]

            if imageData is not None:
                data["imageHeight"], data["imageWidth"] = self._check_image_height_and_width(
                    base64.b64encode(imageData).decode("utf-8"),
                    data.get("imageHeight"),
                    data.get("imageWidth"),
                )

            shapes = [
                dict(
                    label=s["label"],
                    points=s["points"],
                    shape_type=s.get("shape_type", "polygon"),
                    flags=s.get("flags", {}),
                    group_id=s.get("group_id"),
                    other_data={
                        k: v for k, v in s.items() if k not in shape_keys
                    },
                )
                for s in data["shapes"]
            ]
        except Exception as e:
            raise LabelFileError(e)

        otherData = {}
        for key, value in data.items():
            if key not in keys:
                otherData[key] = value

        # Only replace data after everything is loaded.
        self.flags = flags
        self.shapes = shapes
        self.imagePath = imagePath
        self.imageData = imageData
        self.filename = filename
        self.otherData = otherData

    @staticmethod
    def _check_image_height_and_width(imageData, imageHeight, imageWidth):
        img_arr = utils.img_b64_to_arr(imageData)
#        if imageHeight is not None and img_arr.shape[0] != imageHeight:
#            logger.error(
#                "imageHeight does not match with imageData or imagePath, "
#                "so getting imageHeight from actual image."
#            )
        imageHeight = img_arr.shape[0]
#        if imageWidth is not None and img_arr.shape[1] != imageWidth:
#            logger.error(
#                "imageWidth does not match with imageData or imagePath, "
#                "so getting imageWidth from actual image."
#            )
        imageWidth = img_arr.shape[1]

        return imageHeight, imageWidth

    def save(
        self,
        filename,
        shapes,
        imagePath,
        imageHeight,
        imageWidth,
        imageData=None,
        otherData=None,
        flags=None,
    ):
        if imageData is not None:
            imageData = base64.b64encode(imageData).decode("utf-8")
            imageHeight, imageWidth = self._check_image_height_and_width(
                imageData, imageHeight, imageWidth
            )
        if otherData is None:
            otherData = {}
        if flags is None:
            flags = {}
        data = dict(
            version=__version__,
            flags=flags,
            shapes=shapes,
            imagePath=imagePath,
            imageData=imageData,
            imageHeight=imageHeight,
            imageWidth=imageWidth,
        )
        for key, value in otherData.items():
            assert key not in data
            data[key] = value
        try:
            with open(filename, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.filename = filename
        except Exception as e:
            raise LabelFileError(e)

    @staticmethod
    def is_label_file(filename):
        return osp.splitext(filename)[1].lower() == LabelFile.suffix
