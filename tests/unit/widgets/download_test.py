from __future__ import annotations

import pytest

from labelme._widgets.download import _format_bytes


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "0 B"),
        (1023, "1023 B"),
        (1024, "1 KB"),
        (1536, "2 KB"),
        (1048063, "1023 KB"),
        (1048064, "1.0 MB"),
        (1048576, "1.0 MB"),
        (1572864, "1.5 MB"),
        (1073217535, "1023.5 MB"),
        (1073217536, "1.0 GB"),
        (1610612736, "1.5 GB"),
        (1828519936, "1.7 GB"),
        (1099511627776, "1.0 TB"),
    ],
)
def test_format_bytes(n: int, expected: str) -> None:
    assert _format_bytes(n) == expected
