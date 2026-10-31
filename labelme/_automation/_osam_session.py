from __future__ import annotations

import collections
import time
from typing import TYPE_CHECKING
from typing import Final

import numpy as np
from loguru import logger
from numpy.typing import NDArray

if TYPE_CHECKING:
    import osam


def _elapsed_ms(*, t_start: float) -> float:
    return (time.perf_counter() - t_start) * 1000


class OsamSession:
    _model_name: str
    _model: osam.types.Model | None
    _embedding_cache: collections.deque[tuple[str, osam.types.ImageEmbedding]]

    def __init__(
        self,
        *,
        model_name: str,
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
        *,
        image: NDArray[np.uint8],
        image_id: str,
        points: NDArray[np.floating] | None = None,
        point_labels: NDArray[np.intp] | None = None,
        texts: list[str] | None = None,
    ) -> osam.types.GenerateResponse:
        import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

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
        t_start = time.perf_counter()
        response: osam.types.GenerateResponse = model.generate(
            request=osam.types.GenerateRequest(
                model=model.name,
                image=image,
                image_embedding=image_embedding,
                prompt=prompt,
            )
        )
        logger.info(
            "Generated {} annotations with {!r} in {:.0f} ms",
            len(response.annotations),
            self._model_name,
            _elapsed_ms(t_start=t_start),
        )
        return response

    def _get_or_compute_embedding(
        self, *, image: NDArray[np.uint8], image_id: str
    ) -> osam.types.ImageEmbedding:
        for key, embedding in self._embedding_cache:
            if key == image_id:
                return embedding

        model: osam.types.Model = self._get_or_load_model()
        t_start = time.perf_counter()
        embedding: osam.types.ImageEmbedding = model.encode_image(image=image)
        self._embedding_cache.append((image_id, embedding))
        logger.info(
            "Encoded image {}x{} with {!r} in {:.0f} ms",
            image.shape[1],
            image.shape[0],
            self._model_name,
            _elapsed_ms(t_start=t_start),
        )
        return embedding

    def _get_or_load_model(self) -> osam.types.Model:
        if self._model is None:
            import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

            t_start = time.perf_counter()
            self._model = osam.apis.get_model_type_by_name(self._model_name)()
            logger.info(
                "Loaded {!r} in {:.0f} ms",
                self._model_name,
                _elapsed_ms(t_start=t_start),
            )
        return self._model


# ponytail: process-wide sessions keyed by model, so AI Assist and the AI text
# prompt load a shared model once. Keeps the two most recently used, one per
# control; a third model evicts the oldest, which reloads on its next use.
_SESSIONS: Final[dict[str, OsamSession]] = {}


def get_osam_session(*, model_name: str) -> OsamSession:
    MAX_SESSIONS: Final = 2
    session = _SESSIONS.pop(model_name, None)
    if session is None:
        session = OsamSession(model_name=model_name)
    _SESSIONS[model_name] = session
    while len(_SESSIONS) > MAX_SESSIONS:
        _SESSIONS.pop(next(iter(_SESSIONS)))
    return session


def release_osam_session(*, model_name: str) -> None:
    _SESSIONS.pop(model_name, None)
