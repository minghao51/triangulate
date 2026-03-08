"""Tests for LLM utility helpers."""

from __future__ import annotations

import sys
import types

import pytest

from src.ai.utils import call_llm


@pytest.mark.asyncio
async def test_call_llm_prefers_explicit_config_over_environment(monkeypatch):
    """Per-call config should override environment-derived defaults."""

    captured: dict[str, object] = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(
        "src.ai.utils.get_llm_config",
        lambda: {
            "model": "env-model",
            "api_key": "env-key",
            "base_url": "https://env.example.com",
        },
    )

    fake_module = types.SimpleNamespace(acompletion=fake_acompletion)
    monkeypatch.setitem(sys.modules, "litellm", fake_module)

    await call_llm(
        prompt="hello",
        config={
            "model": "request-model",
            "api_key": "request-key",
            "base_url": "https://request.example.com",
        },
    )

    assert captured["model"] == "request-model"
    assert captured["api_key"] == "request-key"
    assert captured["base_url"] == "https://request.example.com"

