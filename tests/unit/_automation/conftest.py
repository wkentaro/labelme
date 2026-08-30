from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.typing import NDArray


@pytest.fixture(params=[math.pi / 6, -math.pi / 6], ids=["+30deg", "-30deg"])
def rotated_rectangle_angle(*, request: pytest.FixtureRequest) -> float:
    return request.param


@pytest.fixture
def rotated_rectangle_mask(*, rotated_rectangle_angle: float) -> NDArray[np.bool_]:
    cos_a = math.cos(rotated_rectangle_angle)
    sin_a = math.sin(rotated_rectangle_angle)
    half_long, half_short = 10.0, 2.0
    ys, xs = np.mgrid[0:40, 0:40]
    dx = xs - 20.0
    dy = ys - 20.0
    local_x = dx * cos_a + dy * sin_a
    local_y = -dx * sin_a + dy * cos_a
    return (np.abs(local_x) <= half_long) & (np.abs(local_y) <= half_short)
