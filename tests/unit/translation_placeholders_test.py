from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from labelme._locale import TRANSLATE_DIR


@pytest.mark.parametrize("ts_path", sorted(TRANSLATE_DIR.glob("*.ts")), ids=str)
def test_translations_keep_placeholders(*, ts_path: Path) -> None:
    # A translation that drops or adds a placeholder shows it literally or
    # raises when the source string is formatted.
    placeholder = re.compile(r"%[sn]|\{\w*\}")
    mismatched = []
    for message in ET.parse(ts_path).iter("message"):
        source = message.findtext("source") or ""
        translation = message.findtext("translation") or ""
        if sorted(placeholder.findall(source)) != sorted(
            placeholder.findall(translation)
        ):
            mismatched.append((source, translation))
    assert mismatched == []
