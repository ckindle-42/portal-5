"""A substituted model_hint is a span on the turn, not only a counter."""

from __future__ import annotations

from portal.platform.inference.router.trace import TurnTrace, note_hint_mismatch, start_trace


def test_note_hint_mismatch_lands_on_the_current_turn() -> None:
    trace = start_trace("p5-hintmismatch")
    assert isinstance(trace, TurnTrace)
    note_hint_mismatch(
        workspace="auto-coding",
        hinted="wanted-tag",
        served="other-tag",
        backend="ollama-general",
        path="non_streaming",
    )
    spans = trace.to_dict()["spans"]
    assert spans[-1]["name"] == "model.hint_mismatch"
    assert spans[-1]["hinted"] == "wanted-tag"
    assert spans[-1]["served"] == "other-tag"
    assert spans[-1]["path"] == "non_streaming"
