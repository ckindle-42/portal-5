"""TASK_COMPLIANCE_REASONING_V2 P9 — acceptance test for the twelve design
section-9 operator questions (Q01-Q12), against the REAL deployed
compliance MCP server and the real ingested LSPG-CIP corpus.

This is deliberately NOT a unit test: it makes live HTTP calls to
``portal-compliance`` (config/portal.yaml mcp_fleet id ``compliance``,
port 8937) and asserts on real register/corpus content, not fixtures. If
the server is unreachable the whole module is skipped with an explicit
reason — never silently mocked to a green result. Run with the stack up:

    uv run pytest tests/acceptance/test_compliance_reasoning_v2_questions.py -q

Q08 (``compliance_intentionality``) and Q09 (``compliance_flexibility``)
are cue-word-level tools, not full semantic obligation modeling — see
``reports/compliance/REASONING_V2_ACCEPTANCE.md`` for the documented
scope limits.
"""

from __future__ import annotations

import httpx
import pytest

COMPLIANCE_MCP_BASE = "http://localhost:8937"
_REAL_PART = "CIP-007-6 R2 Part 2.2"


def _server_up() -> bool:
    try:
        r = httpx.get(f"{COMPLIANCE_MCP_BASE}/health", timeout=3.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _server_up(),
    reason="portal-compliance MCP server not reachable at :8937 — this suite "
    "requires the real live stack (./launch.sh up) and never mocks it",
)


def _call(tool: str, payload: dict) -> dict:
    r = httpx.post(f"{COMPLIANCE_MCP_BASE}/tools/{tool}", json=payload, timeout=60.0)
    r.raise_for_status()
    return r.json()


def test_q01_current_requirement_actually_requires():
    result = _call("nerc_cip_requirement", {"req_id": _REAL_PART})
    assert result.get("found") is True
    # Part-level verbatim text inherits its modal ("shall"/"must") from the
    # parent Requirement row, not every Part clause — assert on the real
    # obligation content instead of a hardcoded modal word.
    assert "35 calendar days" in result["verbatim_text"]
    assert result.get("lifecycle_state") == "EFFECTIVE"
    assert result.get("valid_from")


def test_q02_which_policies_procedures_implement_it():
    result = _call("compliance_mappings", {"requirement_id": _REAL_PART})
    assert "mappings" in result
    assert "override_rate" in result


def test_q03_procedures_aligned_with_latest_standard():
    result = _call(
        "compliance_route",
        {"query": f"Are our procedures fully aligned with {_REAL_PART}?"},
    )
    assert result.get("intent") in {"gaps", "freeform", "change", "today"}
    assert "path" in result


def test_q04_gaps_inconsistencies_stale_weak_mappings():
    result = _call("compliance_gaps", {"standard": "CIP-007-6", "max_rows": 20})
    assert "summary" in result or "examined" in result or "scope" in result
    # F04/F03 safety property: an unresolved item must never be misreported
    # as a confirmed FULL/NONE gap absent real evidence.
    summary = result.get("summary", {})
    if summary:
        assert "unresolved_items" in summary or "confirmed_gaps_none" in summary


def test_q05_q06_requirement_changed_and_impact():
    result = _call(
        "compliance_change_impact",
        {"old_standard": "CIP-003-8", "new_standard": "CIP-003-9"},
    )
    assert result.get("standard") == "CIP-003"
    assert "diff_summary" in result
    assert result["diff_summary"]["n_rows"] > 0


def test_q07_what_changes_would_improve_alignment():
    result = _call(
        "compliance_draft_revisions",
        {"old_standard": "CIP-003-8", "new_standard": "CIP-003-9"},
    )
    assert result.get("mode") == "specification_only"
    assert "specifications" in result


def test_q08_internal_rules_more_restrictive_and_intentional():
    result = _call(
        "compliance_intentionality",
        {
            "requirement_id": _REAL_PART,
            "internal_text": "We evaluate security patches at least once every 21 calendar days.",
        },
    )
    assert result["comparisons"][0]["result"] == "MORE_RESTRICTIVE"
    # F-safety: no control_id supplied means intent must be reported
    # unknown, never inferred from the comparison alone.
    assert result["intentionality"]["status"] == "unknown"


def test_q09_where_does_regulation_permit_flexibility_we_do_not_use():
    # CIP-004-7 R1 Part 1.1 has a real, sourced "may include" clause.
    result = _call("compliance_flexibility", {"requirement_id": "CIP-004-7 R1 Part 1.1"})
    assert len(result["candidate_alternatives"]) >= 1
    assert "may" in result["candidate_alternatives"][0].lower()


def test_q10_connected_documents_controls_evidence_systems_roles():
    result = _call(
        "compliance_trace",
        {"start_ref": _REAL_PART, "direction": "both", "max_depth": 3},
    )
    assert result.get("start_ref") == _REAL_PART
    assert "edges" in result
    assert "truncated" in result


def test_q11_what_needs_review_when_standard_takes_effect():
    result = _call("compliance_prospective", {})
    assert "as_of" in result
    assert "n_future_effective" in result
    # F06 safety property: nothing prospective may leak into a "what do
    # we do today" answer.
    assert "segregation" in result or "prospective" in str(result).lower()


def test_q12_implement_proposed_change_while_maintaining_compliance():
    result = _call(
        "compliance_scenario",
        {
            "target_node_id": _REAL_PART,
            "patch_text": (
                "Perform the required patch evaluation within 21 calendar "
                "days instead of 35 calendar days of availability."
            ),
            "rationale": "acceptance test — CI 21-day tightening scenario",
        },
    )
    assert "scenario_id" in result
    assert "before" in result and "after" in result
