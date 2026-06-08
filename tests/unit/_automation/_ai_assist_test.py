from __future__ import annotations

from collections.abc import Callable

import numpy as np
import osam
import pytest

from labelme._automation import _ai_assist
from labelme._automation._ai_assist import AiAssistSession
from labelme._shape import Shape


@pytest.fixture
def install_fake_osam_session(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[osam.types.GenerateResponse], list[str]]:
    def _install(response: osam.types.GenerateResponse) -> list[str]:
        created_model_names: list[str] = []

        class _FakeOsamSession:
            def __init__(self, model_name: str) -> None:
                self.model_name = model_name
                created_model_names.append(model_name)

            def run(self, **_: object) -> osam.types.GenerateResponse:
                return response

        monkeypatch.setattr(_ai_assist, "OsamSession", _FakeOsamSession)
        return created_model_names

    return _install


def _propose(session: AiAssistSession) -> list[Shape]:
    return session.propose_shapes(
        image=np.zeros((1, 1, 3), dtype=np.uint8),
        image_id="img",
        points=np.zeros((1, 2)),
        point_labels=np.array([1]),
        existing_shapes=[],
    )


def test_propose_shapes_sorts_by_score_and_reuses_session(
    install_fake_osam_session: Callable[[osam.types.GenerateResponse], list[str]],
) -> None:
    response = osam.types.GenerateResponse(
        model="stub",
        annotations=[
            osam.types.Annotation(
                score=0.3,
                bounding_box=osam.types.BoundingBox(
                    xmin=100, ymin=100, xmax=110, ymax=110
                ),
            ),
            osam.types.Annotation(
                score=0.9,
                bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10),
            ),
        ],
    )
    created_model_names = install_fake_osam_session(response)
    session = AiAssistSession(model_name="a", output_format="rectangle")

    shapes = _propose(session)

    assert [shape.shape_type for shape in shapes] == ["rectangle", "rectangle"]
    # Detections are sorted by score descending, so the 0.9 box comes first.
    np.testing.assert_array_equal(shapes[0].points, [[0, 0], [10, 10]])

    _propose(session)
    assert created_model_names == ["a"]

    session.model_name = "b"
    _propose(session)
    assert created_model_names == ["a", "b"]


def test_default_model_name_and_output_format() -> None:
    session = AiAssistSession()
    assert session.model_name == "sam2:latest"
    assert session.output_format == "polygon"

    session.model_name = "efficientsam:latest"
    session.output_format = "mask"
    assert session.model_name == "efficientsam:latest"
    assert session.output_format == "mask"
