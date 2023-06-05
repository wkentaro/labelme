import pickle

import cv2
import torch
import numpy as np
import qimage2ndarray
from qtpy import QtCore

from labelme.logger import logger
from labelme.shape import Shape
import yaml
# segment anything

from segment_anything import sam_model_registry, SamPredictor

def colormap():
    color = Shape.mask_color()
    _colormap = np.array([[0,0,0,0], [color.red(), color.green(), color.blue(), color.alpha()]], dtype=int)
    return _colormap

class Prompt(object):
    def __init__(self):
        self._points = []
        self._labels = []
        self._box = None
        self._mask = None
        self.current_shape = None
        self._shapes = []

    def add_point(self, point: QtCore.QPoint, label: int):
        self._points.append((point.x(), point.y()))
        self._labels.append(label)

    def add_shape(self, shape: Shape):
        self.current_shape = shape
        self._shapes.append(shape)

    def __len__(self):
        return len(self._points)

    @property
    def shapes(self):
        return self._shapes

    @property
    def points(self):
        return np.array(self._points, dtype=float)

    @property
    def labels(self):
        return np.array(self._labels, dtype=float)

    @property
    def box(self):
        return self._box

    @property
    def mask(self):
        return self._mask
    
    @property
    def shapes(self):
        return self._shapes

    def empty(self):
        if len(self._points) == 0 and len(self._labels) == 0 and len(self._box) == 0 and len(self._mask) == 0:
            return True
        else:
            return False
        
    def reset(self):
        self._points = np.array([], dtype=float)
        self._labels = np.array([], dtype=float)
        self._box = None
        self._mask = None
        self.current_shape = None
        self._shapes = []


class Predictor(SamPredictor):
    def __init__(self, model_type, checkpoint, device, config=None) -> None:
        logger.debug(f"Loading Segment Anything Model {model_type} From {checkpoint}, device: {device}")
        if isinstance(device, str):
            self._device = torch.device(device)
        elif isinstance(device, torch.device):
            self._device = device
        sam = sam_model_registry[model_type](checkpoint=checkpoint)
        sam.to(self._device)
        super().__init__(sam)
        if config is not None:
            if isinstance(config, str):
                with open(config, 'r') as f:
                    self.cfg = yaml.safe_load(f)
            else:
                self.cfg = config
        logger.debug(f"set_torch_image input must be BCHW with long side {self.model.image_encoder.img_size}.")

    def predict_embeddings(self, qimage, image_format="RGB", fpath : str =None):
        logger.debug('start')
        if qimage.depth() == 32:
            image = qimage2ndarray.rgb_view(qimage)
        elif qimage.depth() == 8:
            image = cv2.cvtColor(qimage2ndarray.byte_view(qimage), cv2.COLOR_GRAY2RGB)
        else:
            image = qimage2ndarray.rgb_view(qimage)
        self.set_image(image, image_format=image_format)
        if fpath is not None and fpath != "":
            data = {
                'original_size': self.original_size,
                'input_size': self.input_size,
                'embeddings': self.features.cpu().numpy()
            }
            logger.debug(f'save embeddings as {fpath}')
            with open(fpath, 'wb') as f:
                pickle.dump(data, f)
        logger.debug('end')

    def set_embeddings(self, fpath):
        logger.debug('start')
        logger.debug(f'Loading embeddings from {fpath}')
        self.reset_image()
        with open(fpath, 'rb') as f:
            data = pickle.load(f)
        embeddings = data['embeddings']
        self.original_size = data['original_size']
        self.input_size = data['input_size']
        self.features = torch.from_numpy(embeddings).to(self._device)
        self.is_image_set = True
        logger.debug('end')

    def postproc(self, masks, scores, logits, multimask_output):
        logger.debug(f'postproc start')
        if multimask_output:
            idx = np.argmax(scores)
        else:
            idx = 0
        mask = masks[idx].astype(np.uint8)
        logger.debug(f"mask: {mask.shape} {mask.dtype} {np.unique(mask.flatten())}")
        contours, _ = cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) <= 0:
            return None, None, None
        # 找所有轮廓加起来的凸包，获取外接矩形
        points = np.array([point for contour in contours for point in contour], contours[0].dtype)
        x, y, w, h = cv2.boundingRect(points)
        (cx, cy), (rw, rh), ra = cv2.minAreaRect(points)
        logger.debug(f'{cx}, {cy}, {rw}, {rh} ,{ra}')
        tl = QtCore.QPoint(x, y)
        br = QtCore.QPoint(x+w, y+h)
        colorful_mask = colormap()[mask]
        # 把 mask 转换成彩色的 QImage，显示用
        mask_qimg = qimage2ndarray.array2qimage(colorful_mask)
        logger.debug(f'postproc end')
        return tl, br, ((cx, cy), (rw, rh), ra), mask_qimg
    
    def __call__(self, 
                input_point: np.ndarray = None, 
                input_label: np.ndarray = None, 
                input_box: np.ndarray = None,
                input_mask: np.ndarray = None) -> tuple:
        return self.predict(input_point, input_label, input_box, input_mask)
    
    def predict(self, 
                input_points: np.ndarray = None, 
                input_labels: np.ndarray = None, 
                input_box: np.ndarray = None,
                input_mask: np.ndarray = None) -> tuple:
        """
        使用 sam 预测一个矩形框，支持多个提示点，单个提示框，可同时使用

        Args:
            input_points (ndarray): 提示点坐标, shape: (n, 2), dtype: float
            input_labels (ndarray): 0: 背景点, 1: 前景点。shape: (n, ), dtype: float
            input_box (ndarray): 提示框, shape: (1, 4), dtype: float
            input_mask (ndarray): 提示掩码, shape: (1, height, width)
        Return:
            tl (QtCore.QPoint): 框左上角
            br (QtCore.QPoint): 右下角
            mask (QtGui.QImage): 彩色掩码 (RGBA)
        """
        logger.debug(f'start')
        if self.model is None:
            logger.error("predictor is None")
            return None
        if input_points is None and input_labels is None:
            return None
        if isinstance(input_points, list):
            input_points = np.array(input_points)
        if isinstance(input_labels, list):
            input_labels = np.array(input_labels)
        
        logger.debug(f"input_point: {type(input_points)} {input_points.shape} \n{input_points}")
        logger.debug(f"input_label: {type(input_labels)} {input_labels.shape} \n{input_labels}")
        multimask_output = True if input_points.shape[0] > 1 else False
        masks, scores, logits = super().predict(
            point_coords=input_points,
            point_labels=input_labels,
            box=input_box,
            mask_input=input_mask,
            multimask_output=multimask_output,
        )
        
        result = self.postproc(masks, scores, logits, multimask_output)
        logger.debug(f'end')
        return result