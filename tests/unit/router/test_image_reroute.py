"""Unit tests for the text-seat image reroute (Phase 4d) and its interaction
with the existing auto-vision text-only fallback (Phase 4).

All config is monkeypatched — no network, no real backends.
"""

from __future__ import annotations

from typing import Any

import pytest

from portal.platform.inference.config import load_portal_config
from portal.platform.inference.router import preinject as pi

_VISION = frozenset({"vl-seat:tag", "gemma4:26b-a4b-it-qat-ctx16k"})
_TEXT_SEAT = "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k"


def _image_body() -> dict[str, Any]:
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is in this image?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
                ],
            }
        ]
    }


@pytest.fixture(autouse=True)
def _vision_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pi, "_VISION_GROUP_MODELS", _VISION)


def test_image_turn_on_text_only_seat_reroutes_to_auto_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(pi.WORKSPACES, "auto-daily", {"model_hint": _TEXT_SEAT})
    body = _image_body()
    ws_id, out = pi._resolve_text_seat_image_reroute("auto-daily", body)
    assert ws_id == "auto-vision"
    assert out["messages"][0]["role"] == "system"
    assert "rerouted" in out["messages"][0]["content"]
    # The image part survives for the vision seat.
    assert any(
        p.get("type") == "image_url"
        for m in out["messages"]
        for p in (m.get("content", []) if isinstance(m.get("content"), list) else [])
    )


def test_text_turn_on_text_only_seat_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(pi.WORKSPACES, "auto-daily", {"model_hint": _TEXT_SEAT})
    body = {"messages": [{"role": "user", "content": "plain text question"}]}
    ws_id, out = pi._resolve_text_seat_image_reroute("auto-daily", body)
    assert ws_id == "auto-daily"
    assert out == body


def test_vision_capable_seat_with_image_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(pi.WORKSPACES, "auto-daily", {"model_hint": "gemma4:26b-a4b-it-qat-ctx16k"})
    body = _image_body()
    ws_id, out = pi._resolve_text_seat_image_reroute("auto-daily", body)
    assert ws_id == "auto-daily"
    assert out == body


def test_auto_vision_text_only_fallback_unchanged() -> None:
    body = {"messages": [{"role": "user", "content": "what can you do?"}]}
    ws_id, out = pi._resolve_vision_fallback("auto-vision", body)
    assert ws_id == "auto-reasoning"
    assert out["messages"][0]["role"] == "system"
    assert "vision AI assistant" in out["messages"][0]["content"]


def test_auto_vision_with_image_untouched_by_both_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(pi.WORKSPACES, "auto-vision", {"model_hint": "vl-seat:tag"})
    body = _image_body()
    assert pi._resolve_vision_fallback("auto-vision", body) == ("auto-vision", body)
    assert pi._resolve_text_seat_image_reroute("auto-vision", body) == ("auto-vision", body)


def test_reroute_note_skipped_when_system_message_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(pi.WORKSPACES, "auto-daily", {"model_hint": _TEXT_SEAT})
    body = _image_body()
    body["messages"] = [{"role": "system", "content": "persona prompt"}, *body["messages"]]
    _ws_id, out = pi._resolve_text_seat_image_reroute("auto-daily", body)
    assert sum(1 for m in out["messages"] if m.get("role") == "system") == 1


def test_earlier_turn_image_still_reroutes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Any-turn scan: the follow-up is about the pasted image, so the vision
    # seat must serve it even though this turn is text-only.
    monkeypatch.setitem(pi.WORKSPACES, "auto-daily", {"model_hint": _TEXT_SEAT})
    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "see screenshot"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
                ],
            },
            {"role": "assistant", "content": "earlier answer"},
            {"role": "user", "content": "now summarize it in words"},
        ]
    }
    ws_id, _out = pi._resolve_text_seat_image_reroute("auto-daily", body)
    assert ws_id == "auto-vision"


def test_unknown_workspace_with_image_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _image_body()
    ws_id, out = pi._resolve_text_seat_image_reroute("not-a-workspace", body)
    assert ws_id == "not-a-workspace"
    assert out == body


def test_text_only_variant_on_vision_base_reroutes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Phase 4d runs after variant resolution, so the synthetic ::variant key's
    # merged (text-only) model_hint is what gets checked.
    monkeypatch.setitem(pi.WORKSPACES, "ws-vision-base::text-variant", {"model_hint": _TEXT_SEAT})
    ws_id, _out = pi._resolve_text_seat_image_reroute("ws-vision-base::text-variant", _image_body())
    assert ws_id == "auto-vision"


def test_live_config_seats_classify_as_declared(monkeypatch: pytest.MonkeyPatch) -> None:
    """The config-level contract of the seat change: auto-daily's seat is the
    text-only Nemotron tag outside the vision group, while the vision lane and
    the gemma variants stay vision-capable. Reads repo config only."""
    monkeypatch.setattr(pi, "_VISION_GROUP_MODELS", None)
    vision = pi._vision_group_models()
    daily = pi.WORKSPACES["auto-daily"]
    assert daily["model_hint"] == (
        "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k"
    )
    assert daily["model_hint"] not in vision
    assert pi.WORKSPACES["auto-vision"]["model_hint"] in vision
    variants = load_portal_config().workspaces["auto-daily"].variants or {}
    assert variants["gemma-fast"]["model_hint"] in vision
    for name in ("fast", "deep", "nemotron"):
        assert variants[name]["model_hint"] not in vision
