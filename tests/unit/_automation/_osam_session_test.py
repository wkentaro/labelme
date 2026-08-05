from __future__ import annotations

from collections.abc import Callable

import numpy as np
import osam
import pytest
from numpy.typing import NDArray

from labelme._automation._osam_session import OsamSession

_IMAGE: NDArray[np.uint8] = np.zeros((2, 3, 3), dtype=np.uint8)
_POINTS: NDArray[np.floating] = np.array([[1.0, 2.0]])
_POINT_LABELS: NDArray[np.intp] = np.array([1])


class _FakeModelRegistry:
    def __init__(self, *, encode_raises: bool) -> None:
        self.encode_raises = encode_raises
        self.models: list[_FakeModel] = []

    @property
    def model(self) -> _FakeModel:
        return self.models[0]


class _FakeModel:
    name = "fake-model"

    def __init__(self, registry: _FakeModelRegistry) -> None:
        self._registry = registry
        self.encode_calls = 0
        self.requests: list[osam.types.GenerateRequest] = []
        registry.models.append(self)

    def encode_image(self, image: NDArray[np.uint8]) -> osam.types.ImageEmbedding:
        if self._registry.encode_raises:
            raise NotImplementedError
        self.encode_calls += 1
        return osam.types.ImageEmbedding(
            original_height=image.shape[0],
            original_width=image.shape[1],
            embedding=np.zeros((1, 1, 1), dtype=np.float32),
        )

    def generate(
        self, request: osam.types.GenerateRequest
    ) -> osam.types.GenerateResponse:
        self.requests.append(request)
        return osam.types.GenerateResponse(model=self.name, annotations=[])


@pytest.fixture
def install_fake_model(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., _FakeModelRegistry]:
    def _install(*, encode_raises: bool = False) -> _FakeModelRegistry:
        registry = _FakeModelRegistry(encode_raises=encode_raises)
        monkeypatch.setattr(
            osam.apis,
            "get_model_type_by_name",
            lambda name: (lambda: _FakeModel(registry)),
        )
        return registry

    return _install


def _run_point(session: OsamSession, image_id: str) -> None:
    session.run(
        image=_IMAGE,
        image_id=image_id,
        points=_POINTS,
        point_labels=_POINT_LABELS,
    )


def test_point_prompt_carries_points_through_to_generate(
    install_fake_model: Callable[..., _FakeModelRegistry],
) -> None:
    registry = install_fake_model()

    _run_point(OsamSession(model_name="x"), image_id="img")

    (request,) = registry.model.requests
    assert request.prompt is not None
    np.testing.assert_array_equal(request.prompt.points, _POINTS)
    np.testing.assert_array_equal(request.prompt.point_labels, _POINT_LABELS)
    assert request.prompt.texts is None


def test_text_prompt_uses_detection_thresholds(
    install_fake_model: Callable[..., _FakeModelRegistry],
) -> None:
    registry = install_fake_model()

    OsamSession(model_name="x").run(
        image=_IMAGE,
        image_id="img",
        texts=["cat"],
    )

    (request,) = registry.model.requests
    assert request.prompt is not None
    assert request.prompt.texts == ["cat"]
    assert request.prompt.iou_threshold == 1.0
    assert request.prompt.score_threshold == 0.01
    assert request.prompt.max_annotations == 1000


def test_run_without_a_prompt_raises_and_never_generates(
    install_fake_model: Callable[..., _FakeModelRegistry],
) -> None:
    registry = install_fake_model()

    with pytest.raises(ValueError, match="points and point_labels, or texts"):
        OsamSession(model_name="x").run(image=_IMAGE, image_id="img")

    assert registry.model.requests == []


def test_points_without_labels_is_not_treated_as_a_prompt(
    install_fake_model: Callable[..., _FakeModelRegistry],
) -> None:
    registry = install_fake_model()

    with pytest.raises(ValueError, match="points and point_labels, or texts"):
        OsamSession(model_name="x").run(image=_IMAGE, image_id="img", points=_POINTS)

    assert registry.model.requests == []


def test_embedding_is_reused_for_a_repeated_image_id(
    install_fake_model: Callable[..., _FakeModelRegistry],
) -> None:
    registry = install_fake_model()
    session = OsamSession(model_name="x")

    _run_point(session, image_id="img")
    _run_point(session, image_id="img")

    assert registry.model.encode_calls == 1
    assert len(registry.model.requests) == 2


def test_embedding_cache_evicts_by_insertion_order_not_recency(
    install_fake_model: Callable[..., _FakeModelRegistry],
) -> None:
    registry = install_fake_model()
    session = OsamSession(model_name="x", embedding_cache_size=2)

    _run_point(session, image_id="a")
    _run_point(session, image_id="b")
    _run_point(session, image_id="a")
    assert registry.model.encode_calls == 2

    _run_point(session, image_id="c")
    _run_point(session, image_id="a")
    assert registry.model.encode_calls == 4


def test_model_is_loaded_once_and_reused_across_runs(
    install_fake_model: Callable[..., _FakeModelRegistry],
) -> None:
    registry = install_fake_model()
    session = OsamSession(model_name="x")

    _run_point(session, image_id="a")
    _run_point(session, image_id="b")

    assert len(registry.models) == 1


def test_unencodable_model_falls_back_to_no_embedding(
    install_fake_model: Callable[..., _FakeModelRegistry],
) -> None:
    registry = install_fake_model(encode_raises=True)

    _run_point(OsamSession(model_name="x"), image_id="img")

    (request,) = registry.model.requests
    assert request.image_embedding is None
