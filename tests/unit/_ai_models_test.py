from __future__ import annotations

import pytest

from labelme import _ai_models


def test_model_allowlist_is_disabled_when_environment_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LABELME_AI_MODEL_ALLOWLIST", raising=False)

    assert _ai_models.is_model_available(model_name="sam3:latest") is True


def test_model_allowlist_restricts_available_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LABELME_AI_MODEL_ALLOWLIST", "sam2:latest")

    assert _ai_models.is_model_available(model_name="sam2:latest") is True
    assert _ai_models.is_model_available(model_name="sam3:latest") is False


def test_unavailable_model_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LABELME_AI_MODEL_ALLOWLIST", "sam2:latest")

    with pytest.raises(ValueError, match="not included"):
        _ai_models.require_model_available(model_name="sam3:latest")
