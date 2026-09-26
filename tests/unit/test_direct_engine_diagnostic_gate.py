"""TASK_AUTO_COUNCIL_PIPELINE_REVISIT_V1 P1.5: no per-module direct-Ollama
bypass switch (CHAIN_DIRECT_OLLAMA, BLUE_DIRECT_OLLAMA, REFUSAL_DIRECT_OLLAMA,
DRIFT_DIRECT_OLLAMA) may take a product/qualification run off the pipeline
by itself — the shared PORTAL_SECURITY_DIRECT_ENGINE_DIAGNOSTIC gate must
also be set. This is the regression test for that contract: the switch
alone (the exact "stray env var" failure mode the task doc names) must have
no effect.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core._direct_engine_diagnostic import (
    GATE_ENV_VAR,
    direct_engine_diagnostic_enabled,
)

_SWITCHES = [
    "CHAIN_DIRECT_OLLAMA",
    "BLUE_DIRECT_OLLAMA",
    "REFUSAL_DIRECT_OLLAMA",
    "DRIFT_DIRECT_OLLAMA",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(GATE_ENV_VAR, raising=False)
    for switch in _SWITCHES:
        monkeypatch.delenv(switch, raising=False)


@pytest.mark.parametrize("switch", _SWITCHES)
def test_switch_alone_has_no_effect(monkeypatch, switch):
    monkeypatch.setenv(switch, "true")
    assert direct_engine_diagnostic_enabled(switch) is False


@pytest.mark.parametrize("switch", _SWITCHES)
def test_gate_alone_has_no_effect(monkeypatch, switch):
    monkeypatch.setenv(GATE_ENV_VAR, "true")
    assert direct_engine_diagnostic_enabled(switch) is False


@pytest.mark.parametrize("switch", _SWITCHES)
def test_both_switch_and_gate_enable_the_bypass(monkeypatch, switch):
    monkeypatch.setenv(switch, "true")
    monkeypatch.setenv(GATE_ENV_VAR, "true")
    assert direct_engine_diagnostic_enabled(switch) is True


def test_default_product_path_never_reaches_direct_ollama(monkeypatch):
    # No env set at all -- the normal product/qualification state.
    for switch in _SWITCHES:
        assert direct_engine_diagnostic_enabled(switch) is False


def test_one_switch_does_not_enable_a_different_role(monkeypatch):
    # Setting one module's switch plus the shared gate must not leak into
    # another module's diagnostic check.
    monkeypatch.setenv("CHAIN_DIRECT_OLLAMA", "true")
    monkeypatch.setenv(GATE_ENV_VAR, "true")
    assert direct_engine_diagnostic_enabled("BLUE_DIRECT_OLLAMA") is False
