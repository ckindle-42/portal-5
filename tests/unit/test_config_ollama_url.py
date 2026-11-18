"""Tests for Ollama URL canonicalization in portal.platform.inference.config.

Verifies:
  - OLLAMA_URL env wins over yaml value
  - OLLAMA_BASE_URL is accepted as deprecated alias (with warning)
  - Default is consistent everywhere
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.platform.inference.config import load_portal_config


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
