"""Cause C1: every pipeline arm is measured through production's ?model=."""

from __future__ import annotations

import urllib.parse

import pytest

from tests.wfe import campaign, runner


@pytest.fixture
def pipeline_engine(monkeypatch):
    monkeypatch.setattr(runner, "ENGINE", "pipeline")
    monkeypatch.setattr(runner, "CHAT_BASE", "http://pipeline.invalid")


def _query(url: str) -> dict:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def test_pipeline_arm_rides_production_model_override(pipeline_engine):
    url, payload, _ = runner._build_payload(
        "auto-coding", [], {"endpoint": "v1", "pipeline_model": "challenger:7b"}, {}, None, "native"
    )
    assert _query(url) == {"model": ["challenger:7b"]}
    assert payload["model"] == "auto-coding"


def test_pipeline_without_override_is_unchanged(pipeline_engine):
    url, payload, _ = runner._build_payload(
        "auto-coding", [], {"endpoint": "v1"}, {}, None, "native"
    )
    assert "?" not in url and payload["model"] == "auto-coding"


def test_override_id_survives_url_encoding(pipeline_engine):
    tag = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
    url, _, _ = runner._build_payload(
        "auto-compliance", [], {"endpoint": "v1", "pipeline_model": tag}, {}, None, "native"
    )
    assert _query(url)["model"] == [tag]


def test_catalog_matches_production_override_catalog():
    from portal.platform.inference.router.preinject import _known_backend_models

    assert campaign.backend_catalog() == _known_backend_models()


def test_preflight_refuses_model_outside_catalog_without_calling(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("preflight must not call the pipeline for an unservable arm")

    monkeypatch.setattr(campaign, "chat", boom)
    v = campaign.preflight_pipeline(["auto-coding"], "not-a-real-model:1b")
    assert v["verdict"] == "REVIEW" and "not a model id" in v["findings"][0]


def test_preflight_sends_the_arm_as_override(monkeypatch):
    seen = {}
    model = sorted(campaign.backend_catalog())[0]

    def fake_chat(ws, msgs, tools=True, harness=None, **k):
        seen["harness"] = harness
        return {"served": {"model": campaign.seat_primary(ws, model)}}

    monkeypatch.setattr(campaign, "chat", fake_chat)
    campaign.preflight_pipeline(["auto-coding"], model)
    assert seen["harness"] == {"pipeline_model": model}


def test_served_record_carries_the_options_the_pipeline_applied(monkeypatch):
    import io
    import json

    rec = {
        "backend": "omlx-reasoning",
        "model": "granite-4.1-30b-4bit",
        "options_applied": {"temperature": 0.0, "top_k": 20, "repetition_penalty": 1.1},
    }

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        runner.urllib.request, "urlopen", lambda req, timeout=10: R(json.dumps(rec).encode())
    )
    served = runner.pipeline_served("wfe-x")
    assert served == {
        "backend": "omlx-reasoning",
        "model": "granite-4.1-30b-4bit",
        "options": rec["options_applied"],
    }
