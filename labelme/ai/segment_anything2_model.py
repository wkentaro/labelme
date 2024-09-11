import collections
import threading
from typing import Any

import imgviz
import numpy as np
import onnxruntime
import skimage
from numpy import ndarray

from ..logger import logger
from . import _utils


class SegmentAnything2Model:
    """Segmentation model using Segment Anything 2 (SAM2)"""
    def __init__(self, encoder_path, decoder_path) -> None:
        self.model = SegmentAnything2ONNX(encoder_path, decoder_path)
        self._lock = threading.Lock()
        self._image_embedding_cache = collections.OrderedDict()
        self._thread = None

    def set_image(self, image: np.ndarray):
        with self._lock:
            self._image = image
            self._image_embedding = self._image_embedding_cache.get(
                self._image.tobytes()
            )

        if self._image_embedding is None:
            self._thread = threading.Thread(
                target=self._compute_and_cache_image_embedding
            )
            self._thread.start()

    def _compute_and_cache_image_embedding(self):
        with self._lock:
            logger.debug("Computing image embedding...")
            self._image_embedding = self.model.encode(self._image)
            if len(self._image_embedding_cache) > 10:
                self._image_embedding_cache.popitem(last=False)
            self._image_embedding_cache[self._image.tobytes()] = self._image_embedding
            logger.debug("Done computing image embedding.")

    def _get_image_embedding(self):
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        with self._lock:
            return self._image_embedding

    def predict_mask_from_points(self, points, point_labels):
        embedding = self._get_image_embedding()
        masks, scores, orig_im_size = self.model.predict_masks(embedding, points, point_labels)
        best_mask = masks[np.argmax(scores)]
        best_mask = imgviz.resize(best_mask, 
                                  height=orig_im_size[0],
                                  width=orig_im_size[1])
        
        best_mask = np.array([[best_mask]])
        best_mask = best_mask[0,0]
        mask = best_mask > 0.0

        MIN_SIZE_RATIO = 0.05
        skimage.morphology.remove_small_objects(mask, min_size=mask.sum()*MIN_SIZE_RATIO, out=mask)

        return mask

    def predict_polygon_from_points(self, points, point_labels):
        mask = self.predict_mask_from_points(points=points, point_labels=point_labels)
        return _utils.compute_polygon_from_mask(mask=mask)

class SegmentAnything2ONNX:
    """Segmentation model using Segment Anything 2 (SAM2)"""

    def __init__(self, encoder_model_path, decoder_model_path) -> None:
        self.encoder = SAM2ImageEncoder(encoder_model_path)
        self.decoder = SAM2ImageDecoder(
            decoder_model_path, self.encoder.input_shape[2:]
        )

    def encode(self, cv_image: np.ndarray) -> list[np.ndarray]:
        original_size = cv_image.shape[:2]
        high_res_feats_0, high_res_feats_1, image_embed = self.encoder(cv_image)
        return {
            "high_res_feats_0": high_res_feats_0,
            "high_res_feats_1": high_res_feats_1,
            "image_embedding": image_embed,
            "original_size": original_size,
        }

    def predict_masks(self, embedding, points, labels) -> list[np.ndarray]:
        points, labels = np.array(points), np.array(labels)

        image_embedding = embedding["image_embedding"]
        high_res_feats_0 = embedding["high_res_feats_0"]
        high_res_feats_1 = embedding["high_res_feats_1"]
        original_size = embedding["original_size"]
        self.decoder.set_image_size(original_size)
        masks, scores, orig_im_size = self.decoder(
            image_embedding,
            high_res_feats_0,
            high_res_feats_1,
            points,
            labels,
        )

        return masks, scores, orig_im_size

class SAM2ImageEncoder:
    def __init__(self, path: str) -> None:
        # Initialize model
        self.session = onnxruntime.InferenceSession(
            path, providers=onnxruntime.get_available_providers()
        )

        # Get model info
        self.get_input_details()
        self.get_output_details()

    def __call__(
        self, image: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.encode_image(image)

    def encode_image(
        self, image: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        input_tensor = self.prepare_input(image)

        outputs = self.infer(input_tensor)

        return self.process_output(outputs)

    def prepare_input(self, image: np.ndarray) -> np.ndarray:
        self.img_height, self.img_width = image.shape[:2]

        input_img = image[:, :, [2, 1, 0]]
    
    # Resize the image using imgviz
        input_img = imgviz.resize(input_img, height=self.input_height, width=self.input_width)

        mean = np.array([0.485, 0.456, 0.406])
        std = np.array([0.229, 0.224, 0.225])
        input_img = (input_img / 255.0 - mean) / std
        input_img = input_img.transpose(2, 0, 1)
        input_tensor = input_img[np.newaxis, :, :, :].astype(np.float32)

        return input_tensor

    def infer(self, input_tensor: np.ndarray) -> list[np.ndarray]:
        outputs = self.session.run(
            self.output_names, {self.input_names[0]: input_tensor}
        )
        return outputs

    def process_output(
        self, outputs: list[np.ndarray]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return outputs[0], outputs[1], outputs[2]

    def get_input_details(self) -> None:
        model_inputs = self.session.get_inputs()
        self.input_names = [
            model_inputs[i].name for i in range(len(model_inputs))
        ]

        self.input_shape = model_inputs[0].shape
        self.input_height = self.input_shape[2]
        self.input_width = self.input_shape[3]

    def get_output_details(self) -> None:
        model_outputs = self.session.get_outputs()
        self.output_names = [
            model_outputs[i].name for i in range(len(model_outputs))
        ]

class SAM2ImageDecoder:
    def __init__(
        self,
        path: str,
        encoder_input_size: tuple[int, int],
        orig_im_size: tuple[int, int] = None,
        mask_threshold: float = 0.0,
    ) -> None:
        # Initialize model
        self.session = onnxruntime.InferenceSession(
            path, providers=onnxruntime.get_available_providers()
        )

        self.orig_im_size = (
            orig_im_size if orig_im_size is not None else encoder_input_size
        )
        self.encoder_input_size = encoder_input_size
        self.mask_threshold = mask_threshold
        self.scale_factor = 4

        # Get model info
        self.get_input_details()
        self.get_output_details()

    def __call__(
        self,
        image_embed: np.ndarray,
        high_res_feats_0: np.ndarray,
        high_res_feats_1: np.ndarray,
        point_coords: list[np.ndarray] | np.ndarray,
        point_labels: list[np.ndarray] | np.ndarray,
    ) -> tuple[list[np.ndarray], ndarray]:

        return self.predict(
            image_embed,
            high_res_feats_0,
            high_res_feats_1,
            point_coords,
            point_labels,
        )

    def predict(
        self,
        image_embed: np.ndarray,
        high_res_feats_0: np.ndarray,
        high_res_feats_1: np.ndarray,
        point_coords: list[np.ndarray] | np.ndarray,
        point_labels: list[np.ndarray] | np.ndarray,
    ) -> tuple[list[np.ndarray], ndarray]:

        inputs = self.prepare_inputs(
            image_embed,
            high_res_feats_0,
            high_res_feats_1,
            point_coords,
            point_labels,
        )

        outputs = self.infer(inputs)

        return self.process_output(outputs)

    def prepare_inputs(
        self,
        image_embed: np.ndarray,
        high_res_feats_0: np.ndarray,
        high_res_feats_1: np.ndarray,
        point_coords: list[np.ndarray] | np.ndarray,
        point_labels: list[np.ndarray] | np.ndarray,
    ):

        input_point_coords, input_point_labels = self.prepare_points(
            point_coords, point_labels
        )

        num_labels = input_point_labels.shape[0]
        mask_input = np.zeros(
            (
                num_labels,
                1,
                self.encoder_input_size[0] // self.scale_factor,
                self.encoder_input_size[1] // self.scale_factor,
            ),
            dtype=np.float32,
        )
        has_mask_input = np.array([0], dtype=np.float32)

        return (
            image_embed,
            high_res_feats_0,
            high_res_feats_1,
            input_point_coords,
            input_point_labels,
            mask_input,
            has_mask_input,
        )

    def prepare_points(
        self,
        point_coords: list[np.ndarray] | np.ndarray,
        point_labels: list[np.ndarray] | np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:

        if isinstance(point_coords, np.ndarray):
            input_point_coords = point_coords[np.newaxis, ...]
            input_point_labels = point_labels[np.newaxis, ...]
        else:
            max_num_points = max([coords.shape[0] for coords in point_coords])
            # We need to make sure that all inputs have the same number of points
            # Add invalid points to pad the input (0, 0) with -1 value for labels
            input_point_coords = np.zeros(
                (len(point_coords), max_num_points, 2), dtype=np.float32
            )
            input_point_labels = (
                np.ones((len(point_coords), max_num_points), dtype=np.float32)
                * -1
            )

            for i, (coords, labels) in enumerate(
                zip(point_coords, point_labels)
            ):
                input_point_coords[i, : coords.shape[0], :] = coords
                input_point_labels[i, : labels.shape[0]] = labels

        input_point_coords[..., 0] = (
            input_point_coords[..., 0]
            / self.orig_im_size[1]
            * self.encoder_input_size[1]
        )  # Normalize x
        input_point_coords[..., 1] = (
            input_point_coords[..., 1]
            / self.orig_im_size[0]
            * self.encoder_input_size[0]
        )  # Normalize y

        return input_point_coords.astype(np.float32), input_point_labels.astype(
            np.float32
        )

    def infer(self, inputs) -> list[np.ndarray]:
        outputs = self.session.run(
            self.output_names,
            {
                self.input_names[i]: inputs[i]
                for i in range(len(self.input_names))
            },
        )
        return outputs

    def process_output(
        self, outputs: list[np.ndarray]
    ) -> tuple[list[ndarray | Any], ndarray[Any, Any]]:

        scores = outputs[1].squeeze()
        masks = outputs[0][0]

        return (masks,
            scores,
            self.orig_im_size
        )

    def set_image_size(self, orig_im_size: tuple[int, int]) -> None:
        self.orig_im_size = orig_im_size

    def get_input_details(self) -> None:
        model_inputs = self.session.get_inputs()
        self.input_names = [
            model_inputs[i].name for i in range(len(model_inputs))
        ]

    def get_output_details(self) -> None:
        model_outputs = self.session.get_outputs()
        self.output_names = [
            model_outputs[i].name for i in range(len(model_outputs))
        ]
