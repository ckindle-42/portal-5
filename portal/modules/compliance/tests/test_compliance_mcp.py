"""Acceptance: control lookup, CIP map, crosswalk, patch-evidence bridge."""

import importlib
import sys
import types

mod = importlib.import_module("portal.modules.compliance.tools.compliance_mcp")


def test_control_lookup_800_53():
    out = mod.lookup_control("AC-2")
    assert out["found"] and out["id"] == "AC-2"
    assert "Account Management" in out["title"]
    assert "800-53" in out["source"]


def test_control_lookup_csf():
    out = mod.lookup_control("PR.AA-05", framework="csf_2_0")
    assert out["found"] and out["id"] == "PR.AA-05"
    assert "CSF 2.0" in out["source"]


def test_search_controls_returns_citable_ids():
    out = mod.search_controls("least privilege")
    assert out["count"] >= 1
    assert all("id" in c and "title" in c for c in out["controls"])


def test_nerc_cip_requirement_lookup():
    # exact Part -> verbatim text, lifecycle, validity
    for variant in ("CIP-007-6 R2 Part 2.2", "cip-007-6r2part2.2", "CIP-007-6 R2 PART 2.2"):
        out = mod.nerc_cip_requirement(variant)
        assert out["found"], variant
        assert out["granularity"] == "exact"
        assert "35 calendar days" in out["verbatim_text"]
        assert out["lifecycle_state"] == "EFFECTIVE"
        assert out["valid_from"] == "2016-07-01"
    # R-level -> rollup of every Part
    roll = mod.nerc_cip_requirement("CIP-007-6 R2")
    assert roll["found"] and roll["granularity"] == "rollup"
    assert {p["part"] for p in roll["parts"]} == {"2.1", "2.2", "2.3", "2.4"}
    # unknown
    assert not mod.nerc_cip_requirement("CIP-999-1 R1")["found"]


def test_map_frameworks_both_directions():
    fwd = mod.map_frameworks("PR.AA-05", from_fw="csf_2_0", to_fw="nist_800_53")
    assert "AC-2" in fwd["mapped"]
    rev = mod.map_frameworks("AC-2", from_fw="nist_800_53", to_fw="csf_2_0")
    assert "PR.AA-05" in rev["mapped"]
    assert fwd["coverage"] == "partial-seed"


def test_patch_evidence_bridges_triage(monkeypatch):
    fake = types.ModuleType("portal.modules.vulnintel.tools.vulnintel_mcp")
    fake.triage_cve = lambda c, depth="deep": {
        "risk_score": 97,
        "label": "CRITICAL",
        "signals": {"in_kev": True},
        "ssvc_decision": "Act",
    }
    monkeypatch.setitem(sys.modules, "portal.modules.vulnintel.tools.vulnintel_mcp", fake)
    out = mod.patch_evidence("CVE-2021-44228")
    assert out["risk"]["label"] == "CRITICAL" and out["ssvc_decision"] == "Act"
    assert "35 calendar days" in out["cip_007_r2"]


def test_tools_manifest_matches_dispatch():
    assert {t["function"]["name"] for t in mod.TOOLS_MANIFEST} == set(mod._DISPATCH)
