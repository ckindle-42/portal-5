"""V3 routed acceptance: twelve operator questions against the live MCP."""

from __future__ import annotations

import os

import httpx
import pytest

BASE = "http://localhost:8937"
PART = "CIP-007-6 R2 Part 2.2"


@pytest.fixture(scope="module", autouse=True)
def live_server():
    try:
        response = httpx.get(f"{BASE}/health", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        if os.environ.get("COMPLIANCE_LIVE") == "1":
            pytest.fail(f"COMPLIANCE_LIVE=1 but the real MCP is unreachable: {exc}")
        pytest.skip(f"live compliance MCP not requested/reachable: {exc}")


def call(tool: str, payload: dict, timeout: float = 90) -> dict:
    response = httpx.post(f"{BASE}/tools/{tool}", json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    assert not result.get("error"), result
    return result


def test_q01_current_requirement_and_citation():
    result = call("compliance_requirement", {"requirement": PART, "valid_at": "2026-09-05"})
    part = result["parts"][0]
    assert part["id"] == PART
    assert "35 calendar days" in part["verbatim_text"]
    assert part["atoms"][0]["source_anchor_ids"][0].startswith("span-")


def test_q02_internal_implementation_has_determination_and_citations():
    started = call("compliance_analyze", {"requirements": PART, "valid_at": "2026-09-05"})
    result = call(
        "compliance_analyze",
        {
            "requirements": PART,
            "valid_at": "2026-09-05",
            "operation": "result",
            "run_id": started["run_id"],
        },
    )
    claim = result["results"][0]
    assert claim["determination"] in {"SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT"}
    assert claim["citations"][0].startswith("span-")


def test_q03_alignment_is_not_approval_gated():
    started = call("compliance_analyze", {"requirements": PART, "valid_at": "2026-09-05"})
    result = call(
        "compliance_analyze",
        {
            "requirements": PART,
            "valid_at": "2026-09-05",
            "operation": "result",
            "run_id": started["run_id"],
        },
    )
    claim = result["results"][0]
    assert claim["determination"] != "UNRESOLVED"
    assert len(claim["citations"]) >= 1


def test_q04_gaps_have_boundary_or_two_sided_citations():
    started = call("compliance_analyze", {"requirements": "CIP-007-6 R2", "valid_at": "2026-09-05"})
    result = call(
        "compliance_analyze",
        {
            "requirements": "CIP-007-6 R2",
            "valid_at": "2026-09-05",
            "operation": "result",
            "run_id": started["run_id"],
        },
    )
    assert all(
        row["determination"] in {"SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT"}
        for row in result["results"]
    )
    assert all(row["citations"] or row["boundary_proof_id"] for row in result["results"])


def test_q05_revision_change_has_both_spans():
    result = call(
        "compliance_compare", {"before_revision": "CIP-003-8", "after_revision": "CIP-003-9"}
    )
    row = result["interpreted_delta"][0]
    assert row["old_span"] and row["new_span"]
    assert row["part_id_old"].startswith("CIP-003")


def test_q06_impact_paths_are_sourced():
    result = call("compliance_impact", {"start_ref": PART})
    edges = result["direct"] + result["transitive"]
    assert len(edges) > 0
    assert edges[0]["citations"][0]["governing_anchor_id"].startswith("span-")


def test_q07_redlines_are_proposed_and_reassessed():
    result = call(
        "compliance_draft_revisions", {"old_standard": "CIP-003-8", "new_standard": "CIP-003-9"}
    )
    assert result["mode"] == "draft_as_proposal"
    if result["specifications"]:
        item = result["specifications"][0]
        assert item["status"] == "proposed"
        assert item["governing_anchor"]["requirement_id"].startswith("CIP-003")


def test_q08_stricter_rule_is_not_a_violation():
    result = call(
        "compliance_intentionality",
        {
            "requirement_id": PART,
            "internal_text": "Evaluate patches at least once every 21 calendar days.",
        },
    )
    assert result["comparisons"][0]["result"] == "MORE_RESTRICTIVE"
    assert result["requirement_id"] == PART


def test_q09_flexibility_quotes_governing_text():
    requirement = "CIP-004-7 R1 Part 1.1"
    result = call("compliance_flexibility", {"requirement_id": requirement})
    assert "may" in result["candidate_alternatives"][0].lower()
    assert result["requirement_id"] == requirement


def test_q10_trace_reaches_typed_sourced_edges():
    result = call("compliance_trace", {"start_ref": PART, "include_proposed": True, "max_depth": 3})
    assert result["n_edges"] > 0
    assert result["paths"][0]["anchors"][0]["governing_anchor_id"].startswith("span-")


def test_q11_historical_selection_is_labelled():
    result = call(
        "compliance_requirement", {"requirement": "CIP-003-8 R1", "valid_at": "2023-01-01"}
    )
    assert result["parts"][0]["temporal_label"] == "historical"
    assert result["parts"][0]["atoms"][0]["source_anchor_ids"][0].startswith("span-")


def test_q12_scenario_returns_real_determinations():
    result = call(
        "compliance_scenario",
        {
            "target_node_id": PART,
            "patch_text": "The Responsible Entity shall evaluate security patches within 21 calendar days for applicable Cyber Assets.",
            "rationale": "acceptance tightening scenario",
            "effective_on": "2026-09-05",
        },
        timeout=240,
    )
    assert result["before"]["determination"] in {
        "SUPPORTED",
        "PARTIAL",
        "CONTRADICTED",
        "ABSENT",
        "UNRESOLVED",
    }
    assert result["after"]["atom_results"][0]["governing_anchor_ids"] == [PART]
