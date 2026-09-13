"""Workstream F — compliance MCP routing: async gaps, projections, trace, orphans.

Hermetic: no network, no models, no retrieval. The assessment run service and
repository are injected/monkeypatched.
"""

from __future__ import annotations

import dataclasses

import pytest

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.determination import (
    AssessmentResult,
    CoveredCommitment,
    GroundedGap,
)
from portal.modules.compliance.tools import compliance_mcp

SCOPE = AssetScope(impact_present={"high"}, declared_by="operator:test")


def _result(requirement_id: str, coverage: str = "PARTIAL") -> AssessmentResult:
    return AssessmentResult(
        assessment_id=f"assess-{requirement_id}",
        run_id="run-1",
        engine_version="compliance-reading/1",
        input_fingerprint="fp",
        requirement_id=requirement_id,
        applicability="APPLIES",
        documentary_coverage=coverage,
        coverage=coverage,
        substantively_resolved=True,
        covered=[
            CoveredCommitment(
                commitment="evaluate patches",
                governing_slice_ids=["gov-1"],
                internal_slice_ids=["cand-1"],
            )
        ],
        gaps=[
            GroundedGap(
                gap_id="g1",
                kind="WEAKER_COMMITMENT",
                missing_commitment="35-day cadence",
                governing_slice_ids=["gov-1"],
                internal_counterevidence_slice_ids=["cand-2"],
            )
        ],
        selected_source_slices=[
            {
                "slice_id": "gov-1",
                "ref": "CIP-007-6 R2 Part 2.2",
                "document_id": "register",
                "text": "governing text",
                "role": "governing",
            },
            {
                "slice_id": "cand-1",
                "ref": "proc #chunk27 p8",
                "document_id": "proc.pdf",
                "text": "internal support",
                "role": "candidate",
            },
            {
                "slice_id": "cand-2",
                "ref": "proc #chunk27 p8",
                "document_id": "proc.pdf",
                "text": "internal forty day cadence",
                "role": "candidate",
            },
        ],
    )


# ── _compact_citation ───────────────────────────────────────────────────────


def test_compact_citation_prefers_the_canonical_operative_slice():
    spans = [
        {"document_id": "d", "section_id": "s1", "span": "first", "locatable": True},
        {
            "document_id": "d",
            "section_id": "s2",
            "span": "operative",
            "operative": True,
            "locatable": True,
        },
    ]
    assert compliance_mcp._compact_citation(spans)["section"] == "s2"


def test_compact_citation_legacy_falls_back_to_first_locatable():
    spans = [
        {"document_id": "d", "section_id": "s1", "span": "first", "locatable": True},
        {"document_id": "d", "section_id": "s2", "span": "second", "locatable": True},
    ]
    assert compliance_mcp._compact_citation(spans)["section"] == "s1"
    assert compliance_mcp._compact_citation([]) is None


# ── determination projection ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "documentary,expected",
    [
        ("FULL", "SUPPORTED"),
        ("PARTIAL", "PARTIAL"),
        ("NONE", "ABSENT"),
        ("NOT_APPLICABLE", "NOT_APPLICABLE"),
        ("UNRESOLVED", "UNRESOLVED"),
    ],
)
def test_determination_projection(documentary, expected):
    projected = compliance_mcp._determination_projection(
        {
            "requirement_id": "R",
            "documentary_coverage": documentary,
            "coverage": documentary,
            "assessment_id": "a",
        }
    )
    assert projected["determination"] == expected
    assert projected["assessment_id"] == "a"


# ── compliance_gaps async default ───────────────────────────────────────────


def test_gaps_start_returns_run_identity_and_no_rows(monkeypatch):
    from portal.modules.compliance.core import assessment_runs

    monkeypatch.setattr(compliance_mcp, "_gap_requirements", lambda s, r: ["CIP-007-6 R2 Part 2.2"])
    monkeypatch.setattr(compliance_mcp, "_resolve_context_scope", lambda kb, scope: (SCOPE, {}))
    monkeypatch.setattr(assessment_runs, "start_run", lambda request: "run-xyz")
    monkeypatch.setattr(
        assessment_runs, "run_status", lambda run_id: {"run_id": run_id, "status": "QUEUED"}
    )
    out = compliance_mcp.compliance_gaps(requirement="CIP-007-6 R2 Part 2.2")
    assert out["run_id"] == "run-xyz"
    assert out["status"] == "QUEUED"
    assert "rows" not in out


def test_gaps_result_projects_persisted_assessments(monkeypatch):
    from portal.modules.compliance.core import assessment_runs

    audit_rows = [_result("CIP-007-6 R2 Part 2.2"), _result("CIP-007-6 R2 Part 2.3")]
    monkeypatch.setattr(
        assessment_runs,
        "run_result",
        lambda run_id: {
            "run_id": run_id,
            "status": "COMPLETE",
            "engine": "compliance-reading/1",
            "assessment_ids": [r.assessment_id for r in audit_rows],
            "progress": {"completed": 2, "total": 2},
            "results": [dataclasses.asdict(r) for r in audit_rows],
        },
    )
    monkeypatch.setattr(compliance_mcp, "_resolve_context_scope", lambda kb, scope: (SCOPE, {}))
    out = compliance_mcp.compliance_gaps(
        operation="result", run_id="run-1", max_rows=1, generate_drafts=False
    )
    assert out["run_id"] == "run-1"
    assert len(out["rows"]) == 1  # max_rows limits rows
    assert out["summary"]["examined"] == 2  # ... never the assessed summary
    row = out["rows"][0]
    assert row["assessment_id"] == "assess-CIP-007-6 R2 Part 2.2"
    assert row["gaps"][0]["kind"] == "WEAKER_COMMITMENT"
    assert row["policy_citation"]["section"] in ("proc #chunk27 p8", "CIP-007-6 R2 Part 2.2")


def test_gaps_sync_path_uses_injected_results(monkeypatch):
    from portal.modules.compliance.core import assessment_runs

    monkeypatch.setattr(compliance_mcp, "_gap_requirements", lambda s, r: ["X"])
    monkeypatch.setattr(compliance_mcp, "_resolve_context_scope", lambda kb, scope: (SCOPE, {}))
    monkeypatch.setattr(
        assessment_runs, "assess_requirements_now", lambda *a, **k: [_result("X", coverage="FULL")]
    )
    out = compliance_mcp.compliance_gaps(requirement="X", sync=True, generate_drafts=False)
    assert out["rows"][0]["coverage"] == "FULL"
    assert out["summary"]["substantively_resolved"] == 1


# ── compliance_trace recognises an assessment id ────────────────────────────


def test_trace_returns_assessment_and_run_metadata(monkeypatch):
    from portal.modules.compliance.core import repository as repository_mod

    class FakeRepo:
        def get_assessment(self, assessment_id):
            if assessment_id != "assess-1":
                return None
            return {
                "assessment_id": "assess-1",
                "run_id": "run-1",
                "engine_version": "compliance-reading/1",
                "input_fingerprint": "fp",
                "receipt": {"snapshot_fingerprint": "snap"},
            }

        def get_run(self, run_id):
            return {"run_id": run_id, "status": "COMPLETE"}

    monkeypatch.setattr(repository_mod, "Repository", lambda: FakeRepo())
    out = compliance_mcp.compliance_trace("assess-1")
    assert out["kind"] == "assessment"
    assert out["run_metadata"]["snapshot_fingerprint"] == "snap"
    assert out["run"]["status"] == "COMPLETE"


# ── compliance_orphans ──────────────────────────────────────────────────────


def test_orphans_without_a_run_is_inventory_only(monkeypatch):
    monkeypatch.setattr(compliance_mcp, "_all_sections", lambda kb: {"a", "b"})
    out = compliance_mcp.compliance_orphans()
    assert out["inventory_only"] is True
    assert out["proven_orphans"] == []
    assert out["n_sections"] == 2


def test_orphans_with_a_run_uses_resolved_links(monkeypatch):
    from portal.modules.compliance.core import assessment_runs

    monkeypatch.setattr(compliance_mcp, "_all_sections", lambda kb: {"linked", "unlinked"})
    monkeypatch.setattr(
        assessment_runs,
        "run_result",
        lambda run_id: {
            "run_id": run_id,
            "status": "COMPLETE",
            "results": [
                {
                    "requirement_id": "R",
                    "coverage": "FULL",
                    "selected_source_slices": [{"ref": "linked", "document_id": "d"}],
                }
            ],
        },
    )
    out = compliance_mcp.compliance_orphans(run_id="run-1")
    assert out["basis"] == "assessment-run:run-1"
    assert out["orphan_sections"] == ["unlinked"]
