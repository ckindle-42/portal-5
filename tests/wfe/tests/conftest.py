"""WFE unit tests run offline."""

import pytest


@pytest.fixture(autouse=True)
def _offline_wfe(monkeypatch):
    from tests.wfe import campaign, runner

    fixed = {"ollama_version": "test", "host": "test"}
    monkeypatch.setattr(campaign, "env_fingerprint", lambda *a, **k: dict(fixed))
    monkeypatch.setattr(runner, "env_fingerprint", lambda *a, **k: dict(fixed))
    monkeypatch.setattr(runner, "_ollama_can_think", lambda *a, **k: False)
