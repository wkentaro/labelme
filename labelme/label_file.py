import base64
import contextlib
import io
import json
import os.path as osp

import PIL.Image

from labelme import PY2
from labelme import QT4
from labelme import __version__
from labelme import utils
from labelme.logger import logger
from labelme.shape import Shape, ShapeClass

from labelme.widgets.manuscript_type_widget import ManuscriptType

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

    def _loadRecursice(self, data):
        """
            Метод для рекурсивной подгрузки bbox-ов из словаря.
            
            Преобразует поля словаря как это делалось в коде ранее, 
            но с учётом иерархии в bbox.
            
            -------
            Параметры
            
            data
                Список bbox-ов
            
            -------    
            Возвращает 
                
            Преобразованный список
        """
        shape_keys = [
            "label",
            "diacritical",
            "points",
            "shapes",
            "shape_type",
        ]

        shapes = []
        for s in data:
            # Текст
            if "label" not in s and "diacritical" not in s:
                shapes.append(
                    dict(
                        shapes=self._loadRecursice(s["shapes"]),
                        points=s["points"],
                        shape_type=s.get("shape_type", "rectangle"),
                        other_data={k: v for k, v in s.items() if k not in shape_keys},
                    )
                )
            # Строка 
            elif "label" in s and "diacritical" not in s:
                shapes.append(
                    dict(
                        label=s["label"],
                        shapes=self._loadRecursice(s["shapes"]),
                        points=s["points"],
                        shape_type=s.get("shape_type", "rectangle"),
                        other_data={k: v for k, v in s.items() if k not in shape_keys},
                    )
                )
            # Буква
            elif "label" in s and "diacritical" in s:
                shapes.append(
                    dict(
                        label=s["label"],
                        diacritical=s["diacritical"],
                        points=s["points"],
                        shape_type=s.get("shape_type", "rectangle"),
                        other_data={k: v for k, v in s.items() if k not in shape_keys},
                    )
                )
            else:
                raise Exception("error of recognision a .json file in load_recursive")

        return shapes

    def load(self, filename):
        keys = [
            "imagePath",
            "shapes",  # polygonal annotations
            "imageHeight",
            "imageWidth",
            "textType",
        ]
        try:
            with open(filename, "r") as f:
                data = json.load(f)

            imagePath = osp.join(osp.dirname(filename), data["imagePath"])
            imageData = self.load_image_file(imagePath)
            
            if data["textType"] in ManuscriptType:
                textType = ManuscriptType(data["textType"])
            else:
                textType = ManuscriptType.USTAV
                
            imagePath = data["imagePath"]
            self._check_image_height_and_width(
                base64.b64encode(imageData).decode("utf-8"),
                data.get("imageHeight"),
                data.get("imageWidth"),
            )
            shapes = self._loadRecursice(data["shapes"])
        except Exception as e:
            raise LabelFileError(e)

        otherData = {}
        for key, value in data.items():
            if key not in keys:
                otherData[key] = value

        # Only replace data after everything is loaded.
        self.shapes = shapes
        self.imagePath = imagePath
        self.imageData = imageData
        self.filename = filename
        self.otherData = otherData
        self.textType = textType

    @staticmethod
    def _check_image_height_and_width(imageData, imageHeight, imageWidth):
        img_arr = utils.img_b64_to_arr(imageData)
        if imageHeight is not None and img_arr.shape[0] != imageHeight:
            logger.error(
                "imageHeight does not match with imageData or imagePath, "
                "so getting imageHeight from actual image."
            )
            imageHeight = img_arr.shape[0]
        if imageWidth is not None and img_arr.shape[1] != imageWidth:
            logger.error(
                "imageWidth does not match with imageData or imagePath, "
                "so getting imageWidth from actual image."
            )
            imageWidth = img_arr.shape[1]
        return imageHeight, imageWidth

    def save(
        self,
        filename,
        shapes,
        imagePath,
        imageHeight,
        imageWidth,
        otherData=None,
        textType=None,
    ):
        if otherData is None:
            otherData = {}
        if textType is None:
            textType = ManuscriptType.USTAV
        data = dict(
            shapes=shapes,
            imagePath=imagePath,
            imageHeight=imageHeight,
            imageWidth=imageWidth,
            textType=textType.value,
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
