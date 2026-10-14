"""WFE unit tests run offline."""

import pytest


@pytest.fixture(autouse=True)
def _offline_wfe(monkeypatch, tmp_path_factory):
    from tests.wfe import campaign, eval_mode, runner

    # Evaluation-scope seeding and cleanup POST to live MCP ports; tests stub or record them.
    monkeypatch.setattr(eval_mode, "eval_post", lambda url, body: None)
    # Production-mode rows stage under OUTPUT_ROOT: never the developer's real ~/AI_Output.
    monkeypatch.setattr(eval_mode, "OUTPUT_ROOT", tmp_path_factory.mktemp("ai_output"))
    fixed = {"ollama_version": "test", "host": "test"}
    monkeypatch.setattr(campaign, "env_fingerprint", lambda *a, **k: dict(fixed))
    monkeypatch.setattr(runner, "env_fingerprint", lambda *a, **k: dict(fixed))
    monkeypatch.setattr(runner, "_ollama_can_think", lambda *a, **k: False)
    # The developer's tree is often dirty; tests of the gate patch this themselves.
    monkeypatch.setattr(campaign, "instrument_dirty", lambda: [])
    head = campaign._git("rev-parse", "HEAD").strip()
    monkeypatch.setattr(campaign, "deployed_build", lambda: head)
    monkeypatch.setattr(campaign, "deployed_services", lambda: {})
