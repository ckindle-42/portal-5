"""Regression tests for the acceptance harness request contract."""

from __future__ import annotations

from tests.acceptance import _common
from tests.lib.stream_wait import StreamResult, StreamStatus


def test_every_non_benchmark_persona_has_a_smoke_contract() -> None:
    missing = [
        persona["slug"]
        for persona in _common.PERSONAS
        if persona.get("category") not in ("benchmark", "bench")
        and persona["slug"] not in _common.PERSONA_PROMPTS
        and persona["slug"] not in _common.PERSONA_PROMPTS_EXCLUDED
    ]

    assert missing == []


async def test_chat_with_model_preserves_full_system_prompt(monkeypatch) -> None:
    captured: dict = {}

    async def fake_stream_chat(**kwargs):
        captured.update(kwargs)
        return StreamResult(
            status=StreamStatus.OK,
            text="done",
            model="test-model",
            route="auto;ollama;test-model",
        )

    monkeypatch.setattr(_common, "_stream_chat", fake_stream_chat)
    system = "contract-" + ("x" * 1200) + "-required-tail"

    code, text, model, route = await _common._chat_with_model(
        "auto-compliance",
        "Assess this control.",
        system=system,
        idle_gap_s=120,
    )

    assert (code, text, model, route) == (
        200,
        "done",
        "test-model",
        "auto;ollama;test-model",
    )
    assert captured["body"]["messages"][0] == {"role": "system", "content": system}
    assert captured["idle_gap_s"] == 120
