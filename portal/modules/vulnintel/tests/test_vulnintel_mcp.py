"""Acceptance: scoring logic, private-IP guard, CVE-id validation, KEV override."""

import importlib

import pytest

mod = importlib.import_module("portal.modules.vulnintel.tools.vulnintel_mcp")


def test_cve_id_validation():
    with pytest.raises(ValueError):
        mod._norm_cve("not-a-cve")
    assert mod._norm_cve("cve-2024-3400") == "CVE-2024-3400"


def test_private_ip_rejected_before_lookup():
    for ip in ("10.0.0.1", "192.168.1.1", "127.0.0.1", "169.254.1.1"):
        with pytest.raises(ValueError):
            mod._reject_private_ip(ip)


def test_kev_hard_override(monkeypatch):
    # low CVSS, low EPSS, but KEV-listed -> must clamp to CRITICAL / >=76
    monkeypatch.setattr(
        mod, "lookup_cve", lambda c: {"cve_id": c, "cvss": {"baseScore": 2.0}, "description": ""}
    )
    monkeypatch.setattr(mod, "get_epss", lambda c: {"cve_id": c, "epss": 0.01})
    monkeypatch.setattr(mod, "check_kev", lambda c: {"cve_id": c, "in_kev": True})
    out = mod.triage_cve("CVE-2021-44228", depth="deep")
    assert out["label"] == "CRITICAL"
    assert out["risk_score"] >= 76
    assert out["ssvc_decision"] == "Act"


def test_non_kev_low_signal_is_low(monkeypatch):
    monkeypatch.setattr(
        mod, "lookup_cve", lambda c: {"cve_id": c, "cvss": {"baseScore": 1.0}, "description": ""}
    )
    monkeypatch.setattr(mod, "get_epss", lambda c: {"cve_id": c, "epss": 0.0})
    monkeypatch.setattr(mod, "check_kev", lambda c: {"cve_id": c, "in_kev": False})
    out = mod.triage_cve("CVE-2000-0001")
    assert out["label"] in ("LOW", "MEDIUM")
    assert out["risk_score"] < 51


def test_tools_manifest_matches_dispatch():
    manifest_names = {t["function"]["name"] for t in mod.TOOLS_MANIFEST}
    assert manifest_names == set(mod._DISPATCH)
