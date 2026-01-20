from __future__ import annotations

import collections

import numpy as np
import osam
from loguru import logger
from numpy.typing import NDArray


class OsamSession:
    _model_name: str
    _model: osam.types.Model | None
    _embedding_cache: collections.deque[tuple[str, osam.types.ImageEmbedding]]

    def __init__(
        self,
        model_name: str = "sam2:latest",
        embedding_cache_size: int = 3,
    ) -> None:
        logger.debug("Initializing OsamSession with model_name={!r}", model_name)
        self._model_name = model_name
        self._model = None
        self._embedding_cache = collections.deque(maxlen=embedding_cache_size)
        logger.debug("Initialized OsamSession with model_name={!r}", model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    def run(
        self,
        image: NDArray[np.uint8],
        image_id: str,
        points: NDArray[np.floating] | None = None,
        point_labels: NDArray[np.intp] | None = None,
        texts: list[str] | None = None,
    ) -> osam.types.GenerateResponse:
        image_embedding: osam.types.ImageEmbedding | None
        try:
            image_embedding = self._get_or_compute_embedding(
                image=image, image_id=image_id
            )
        except NotImplementedError:
            image_embedding = None

        prompt: osam.types.Prompt
        if points is not None and point_labels is not None:
            prompt = osam.types.Prompt(
                points=points,
                point_labels=point_labels,
            )
        elif texts is not None:
            prompt = osam.types.Prompt(
                texts=texts,
                iou_threshold=1.0,
                score_threshold=0.01,
                max_annotations=1000,
            )
        else:
            raise ValueError(
                "Either points and point_labels, or texts must be provided."
            )

        model: osam.types.Model = self._get_or_load_model()
        return model.generate(
            request=osam.types.GenerateRequest(
                model=model.name,
                image=image,
                image_embedding=image_embedding,
                prompt=prompt,
            )
        )

    def _get_or_compute_embedding(
        self, image: NDArray[np.uint8], image_id: str
    ) -> osam.types.ImageEmbedding:
        for key, embedding in self._embedding_cache:
            if key == image_id:
                return embedding

        model: osam.types.Model = self._get_or_load_model()
        logger.debug("Computing embedding for cache_key={!r}", image_id)
        embedding: osam.types.ImageEmbedding = model.encode_image(image=image)
        self._embedding_cache.append((image_id, embedding))
        logger.debug("Cached embedding for cache_key={!r}", image_id)
        return embedding

    def _get_or_load_model(self) -> osam.types.Model:
        if self._model is None:
            logger.debug("Loading model with name={!r}", self._model_name)
            self._model = osam.apis.get_model_type_by_name(self._model_name)()
            logger.debug("Loaded model with name={!r}", self._model_name)
        return self._model
