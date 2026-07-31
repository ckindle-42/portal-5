"""Slice 1.2 gate: SecurityExecutor is the ground-truth boundary (D2, I1).

Proves: real dispatch is called, scope guard fires before any action leaves
the box, the observation delta never carries the model's predicted
`expected_observation_delta` (narration), and live perception — when bound —
is folded into the delta as ground truth.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.objective_executor import SecurityExecutor
from portal.modules.security.core.perception import LabPerception, OutOfScopeError


def _decision(**overrides) -> dict:
    base = {
        "action": "run_nmap_scan",
        "tool": "run_nmap_scan",
        "args": {"target": "10.10.11.5"},
        "reason": "top-ranked capability match",
        "confidence": 0.7,
        "expected_oracle": None,
        "expected_observation_delta": {"technique_attempted": "run_nmap_scan"},
        "alternatives_considered": [],
        "outcome": "proposed",
    }
    base.update(overrides)
    return base


def test_execute_dispatches_real_tool(monkeypatch):
    calls = []

    def fake_dispatch(fn_name, fn_args, dry_run=False):
        calls.append((fn_name, fn_args, dry_run))
        return "OK: scan complete"

    monkeypatch.setattr("portal.modules.security.core.lab.lab_dispatch", fake_dispatch)

    ex = SecurityExecutor()
    result = ex.execute(_decision(), {"observations": {}, "history": []})

    assert calls == [("run_nmap_scan", {"target": "10.10.11.5"}, False)]
    assert result["raw"] == "OK: scan complete"


@pytest.mark.parametrize(
    "selected_tool",
    [
        "bloodhound-ce-python",
        "enum4linux-ng",
        "impacket-GetNPUsers",
        "impacket-GetUserSPNs",
        "nmap",
        "nxc",
    ],
)
def test_execute_dispatches_only_allowlisted_read_only_binary(monkeypatch, selected_tool):
    calls = []
    monkeypatch.setattr(
        "portal.modules.security.core.lab.lab_dispatch",
        lambda name, args, dry_run=False: calls.append((name, args, dry_run)) or "OK",
    )

    result = SecurityExecutor().execute(
        _decision(action="ldap_probe", tool=selected_tool),
        {"observations": {}, "history": []},
    )

    assert calls == [(selected_tool, {"target": "10.10.11.5"}, False)]
    assert result["observation_delta"]["last_action"] == "ldap_probe"
    assert result["observation_delta"]["last_tool"] == selected_tool


@pytest.mark.parametrize(
    "selected_tool",
    [
        "curl",
        "certipy-ad",
        "impacket-secretsdump",
        "impacket-psexec",
        "impacket-wmiexec",
        "responder",
        "metasploit",
    ],
)
def test_execute_non_allowlisted_binary_retains_capability_fallback(monkeypatch, selected_tool):
    calls = []
    monkeypatch.setattr(
        "portal.modules.security.core.lab.lab_dispatch",
        lambda name, args, dry_run=False: calls.append((name, args, dry_run)) or "UP",
    )

    result = SecurityExecutor().execute(
        _decision(action="smb_probe", tool=selected_tool),
        {"observations": {}, "history": []},
    )

    assert calls == [("smb_probe", {"target": "10.10.11.5"}, False)]
    assert result["observation_delta"]["last_action"] == "smb_probe"
    assert result["observation_delta"]["last_tool"] == "smb_probe"


def test_scope_guard_fires_before_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "portal.modules.security.core.lab.lab_dispatch",
        lambda *a, **k: calls.append(a) or "unreachable",
    )

    ex = SecurityExecutor()
    decision = _decision(args={"target": "8.8.8.8"})
    with pytest.raises(OutOfScopeError):
        ex.execute(decision, {"observations": {}, "history": []})
    assert calls == []  # guard fires before any dispatch leaves the box


def test_observation_delta_never_carries_predicted_delta(monkeypatch):
    monkeypatch.setattr(
        "portal.modules.security.core.lab.lab_dispatch",
        lambda *a, **k: "OK",
    )
    ex = SecurityExecutor()
    decision = _decision(expected_observation_delta={"technique_attempted": "should_never_appear"})
    result = ex.execute(decision, {"observations": {}, "history": []})

    assert "technique_attempted" not in result["observation_delta"]
    assert "should_never_appear" not in str(result["observation_delta"])


def test_oracle_result_from_real_verify_finding(monkeypatch):
    monkeypatch.setattr(
        "portal.modules.security.core.lab.lab_dispatch",
        lambda *a, **k: "reflected payload in response",
    )

    class _FakeVerdict:
        verified = True

    monkeypatch.setattr(
        "portal.modules.security.core.oracles.verify_finding",
        lambda finding, lab_output, observations: _FakeVerdict(),
    )

    ex = SecurityExecutor()
    decision = _decision(expected_oracle="reflection")
    result = ex.execute(decision, {"observations": {}, "history": []})

    assert result["oracle_result"] is True
    assert result["observation_delta"]["oracle:reflection"] is True


def test_perception_folded_into_delta_as_ground_truth(monkeypatch):
    monkeypatch.setattr(
        "portal.modules.security.core.lab.lab_dispatch",
        lambda *a, **k: "OK",
    )
    perception = LabPerception(
        prober=lambda hosts: {
            "services": [{"host": hosts[0], "up": True}],
            "state": {hosts[0]: 1},
        }
    )
    ex = SecurityExecutor(perception=perception)
    result = ex.execute(_decision(), {"observations": {}, "history": []})

    delta = result["observation_delta"]
    assert delta["_source"] == "live_perception"
    assert delta["services"] == [{"host": "10.10.11.5", "up": True}]
