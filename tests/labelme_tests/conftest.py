import pathlib

import pytest


@pytest.fixture(scope="session")
def data_path() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "data"
