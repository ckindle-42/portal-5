"""UAT settings-delivery gate — refuses a UAT that would not measure the
configured seats (no network: every probe is monkeypatched)."""

from __future__ import annotations

import httpx

from tests.uat import settings_gate as g


def _owui(monkeypatch, default_params=None, user_params=None, model_params=None):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/configs/models":
            return httpx.Response(200, json={"DEFAULT_MODEL_PARAMS": default_params or {}})
        if req.url.path == "/api/v1/users/user/settings":
            return httpx.Response(200, json={"ui": {"params": user_params or {}}})
        items = [{"id": "auto-coding", "params": model_params or {"system": "x"}}]
        return httpx.Response(200, json={"items": items, "total": 1})

    real = httpx.Client

    def client(**kw):
        kw.pop("transport", None)
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(g.httpx, "Client", client)


def test_owui_sampling_injection_is_flagged(monkeypatch):
    _owui(monkeypatch, default_params={"temperature": 0.8}, model_params={"top_k": 40})
    problems = g._owui_problems("tok")
    assert any("DEFAULT_MODEL_PARAMS" in p for p in problems)
    assert any("auto-coding" in p and "top_k" in p for p in problems)


def test_clean_owui_passes(monkeypatch):
    _owui(monkeypatch, user_params={"tool_approval_mode": "full"})
    assert g._owui_problems("tok") == []


def test_routing_fail_blocks_and_a_crashing_check_is_not_a_pass(monkeypatch):
    monkeypatch.setattr(g, "_contract_problems", lambda: [])
    monkeypatch.setattr(
        g, "_routing_problems", lambda: ["auto-coding::fast-repair: hint_unroutable — x"]
    )

    def boom(token):
        raise RuntimeError("owui down")

    monkeypatch.setattr(g, "_owui_problems", boom)
    problems = g.settings_gate("tok")
    assert any("hint_unroutable" in p for p in problems)
    assert any("could not run" in p for p in problems)
