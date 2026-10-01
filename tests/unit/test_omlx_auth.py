"""The oMLX API key is sent to oMLX and nowhere else."""

from __future__ import annotations

import httpx
import pytest

from portal.platform.inference import omlx_auth


def _flow(url: str, headers: dict | None = None) -> httpx.Request:
    req = httpx.Request("GET", url, headers=headers or {})
    return next(omlx_auth.OmlxKeyAuth().auth_flow(req))


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch, tmp_path):
    monkeypatch.setattr(omlx_auth, "_ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("OMLX_URL", raising=False)


def test_key_goes_to_omlx_only(monkeypatch):
    monkeypatch.setenv("OMLX_API_KEY", "k1")
    assert (
        _flow("http://host.docker.internal:8085/v1/models").headers["Authorization"] == "Bearer k1"
    )
    assert _flow("http://localhost:8085/v1/models").headers["Authorization"] == "Bearer k1"
    assert "Authorization" not in _flow("http://host.docker.internal:11434/api/tags").headers
    assert "Authorization" not in _flow("http://example.com:8085/v1/models").headers


def test_no_key_adds_nothing(monkeypatch):
    monkeypatch.delenv("OMLX_API_KEY", raising=False)
    assert "Authorization" not in _flow("http://localhost:8085/v1/models").headers


def test_caller_authorization_wins(monkeypatch):
    monkeypatch.setenv("OMLX_API_KEY", "k1")
    req = _flow("http://localhost:8085/x", {"Authorization": "Bearer mine"})
    assert req.headers["Authorization"] == "Bearer mine"


def test_omlx_url_override_is_the_only_target(monkeypatch):
    monkeypatch.setenv("OMLX_API_KEY", "k1")
    monkeypatch.setenv("OMLX_URL", "http://omlx.lan:9000")
    assert "Authorization" in _flow("http://omlx.lan:9000/v1/models").headers
    assert "Authorization" not in _flow("http://localhost:8085/v1/models").headers


def test_key_falls_back_to_env_file(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text('OTHER=1\nOMLX_API_KEY="from-file"\n')
    monkeypatch.setattr(omlx_auth, "_ENV_FILE", env)
    monkeypatch.delenv("OMLX_API_KEY", raising=False)
    assert omlx_auth.omlx_headers() == {"Authorization": "Bearer from-file"}
