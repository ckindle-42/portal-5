"""Tests for Ollama URL canonicalization in portal.platform.inference.config.

Verifies:
  - OLLAMA_URL env wins over yaml value
  - OLLAMA_BASE_URL is accepted as deprecated alias (with warning)
  - Default is consistent everywhere
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from portal.platform.inference.config import load_portal_config, ollama_url

REPO = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def _restore_real_config(monkeypatch: pytest.MonkeyPatch):
    """Restore the real portal.yaml cache before and after each test in this file.

    Clears OLLAMA_URL/OLLAMA_BASE_URL before each test so cross-file env
    pollution doesn't affect assertions that expect the YAML default.
    """
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    load_portal_config(_force_reload=True)
    yield
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    load_portal_config(_force_reload=True)


_MINIMAL_YAML = {
    "ollama_url": "http://yaml-default:11434",
    "mcp_fleet": [],
    "workspaces": {
        "auto": {
            "name": "Auto",
            "description": "test",
            "tools": [],
            "expose_to_owui": True,
            "enable_web_search": False,
        }
    },
}


def _write_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "portal.yaml"
    p.write_text(yaml.dump(_MINIMAL_YAML))
    return p


def test_ollama_url_from_yaml(tmp_path: Path) -> None:
    """Without env override, ollama_url is read from portal.yaml."""
    p = _write_yaml(tmp_path)
    cfg = load_portal_config(path=p, _force_reload=True)
    assert cfg.ollama_url == "http://yaml-default:11434"


def test_ollama_url_env_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OLLAMA_URL env var overrides the yaml value."""
    p = _write_yaml(tmp_path)
    monkeypatch.setenv("OLLAMA_URL", "http://env-host:11434")
    cfg = load_portal_config(path=p, _force_reload=True)
    assert cfg.ollama_url == "http://env-host:11434"


def test_ollama_base_url_deprecated_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """OLLAMA_BASE_URL is accepted as deprecated alias and triggers a warning."""
    p = _write_yaml(tmp_path)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://legacy-host:11434")
    with caplog.at_level(logging.WARNING, logger="portal.platform.inference.config"):
        cfg = load_portal_config(path=p, _force_reload=True)
    assert cfg.ollama_url == "http://legacy-host:11434"
    assert any(
        "OLLAMA_BASE_URL" in r.message and "deprecated" in r.message for r in caplog.records
    ), "Expected a deprecation warning for OLLAMA_BASE_URL"


def test_ollama_url_env_takes_priority_over_base_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When both OLLAMA_URL and OLLAMA_BASE_URL are set, OLLAMA_URL wins."""
    p = _write_yaml(tmp_path)
    monkeypatch.setenv("OLLAMA_URL", "http://winner:11434")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://loser:11434")
    cfg = load_portal_config(path=p, _force_reload=True)
    assert cfg.ollama_url == "http://winner:11434"


def test_ollama_url_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ollama_url() helper returns config.ollama_url with no arg."""
    p = _write_yaml(tmp_path)
    monkeypatch.setenv("OLLAMA_URL", "http://helper-test:11434")
    cfg = load_portal_config(path=p, _force_reload=True)
    assert ollama_url(cfg) == "http://helper-test:11434"


def test_production_config_has_valid_ollama_url() -> None:
    """The actual config/portal.yaml has a non-empty ollama_url."""
    cfg = load_portal_config()
    assert cfg.ollama_url
    assert cfg.ollama_url.startswith("http")


def test_cluster_backends_yaml_uses_ollama_url() -> None:
    """backends.yaml must reference OLLAMA_URL (not a hardcoded non-env URL)."""
    backends = (
        Path(__file__).resolve().parent.parent.parent / "config" / "backends.yaml"
    ).read_text()
    assert "OLLAMA_URL" in backends, (
        "backends.yaml must use ${OLLAMA_URL:-...} so native Ollama on Apple Silicon is reachable"
    )
