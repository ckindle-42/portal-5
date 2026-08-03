"""Regression tests for the authored-unit quality gate.

The gate is the definition of coverage, not a review step afterwards: a unit that
fails any check does not count. These tests pin down the two calibration results
that must hold or the whole authored-coverage program is meaningless:

  calibrate() returns 100% — the gate must never reject the operator's own work;
  every known-bad case is caught — the gate must never pass filler.

Each fake is tagged `authored-v1` so the authored-only checks apply to it.
"""

from __future__ import annotations

from pathlib import Path

from portal.platform.wiki import quality as q
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unit(uid: str, body: str, claims: list[dict] | None = None) -> KnowledgeUnit:
    return KnowledgeUnit(
        id=uid,
        kind="mixed",
        title=uid,
        sources=[SourceRef(type="code", path="portal/platform/wiki/quality.py")],
        body=body,
        claims=claims or [],
        tags=["authored-v1"],
    )


def _issues(units: list[KnowledgeUnit]) -> list[q.QualityIssue]:
    q.reset_universe()
    return list(q.assess(units, REPO_ROOT).issues)


def _assert_flagged(units: list[KnowledgeUnit], uid: str, check: str) -> None:
    issues = [i for i in _issues(units) if i.unit_id == uid]
    assert any(i.check == check for i in issues), (
        f"expected {uid} to be caught by '{check}', got {[str(i) for i in issues]}"
    )


def _good_body() -> str:
    return (
        "This module owns the boundary between the ingress transport and the "
        "egress dispatcher, keeping backpressure out of the model path.\n\n"
        "## Why\n\n"
        "The transport must never decide routing policy, so the boundary layer "
        "separates concerns that would otherwise fuse into one hot path; moving "
        "the decision into the dispatcher would couple the transport to model "
        "selection and break the stateless pipeline contract.\n\n"
        "## Interfaces\n\n"
        "The dispatch entry point is what callers touch; the queue holds work.\n"
    )


# ── known-good calibration ───────────────────────────────────────────────────


def test_calibrate_reports_one_hundred_percent_on_legacy_corpus():
    """The gate must never reject hand-authored work. If this fails, the
    thresholds are wrong, not the corpus."""
    q.reset_universe()
    result = q.calibrate(REPO_ROOT)
    assert result["pass_rate"] == 100.0, result["sample_issues"]


# ── distinctness ─────────────────────────────────────────────────────────────


def test_near_identical_filler_is_caught_by_distinctness():
    body_a = _good_body()
    body_b = _good_body().replace("egress dispatcher", "egress dispatcher too")
    units = [_unit("fake-a", body_a), _unit("fake-b", body_b)]
    _assert_flagged(units, "fake-b", "distinctness")


# ── grounding ────────────────────────────────────────────────────────────────


def test_invented_symbols_are_caught_by_grounding():
    # Symbols are assembled at runtime so their literal tokens never appear in
    # any repo file — the identifier universe is walked across every .py file,
    # so a symbol spelled out in this test file would itself be "grounded".
    stage = "zorp" + "boozle_" + "processor"
    frames = "glorb" + "quad"
    engine = "schnarf_" + "engine"
    reduce = "mimble" + "red"
    fork = "trilo" + "bite_fork"
    dump = "quarkle_" + "dump"
    body = (
        f"The `{stage}` stage takes raw `{frames}` frames and "
        f"passes them to the `{engine}` for `{reduce}` reduction before "
        f"the `{fork}` hands them to `{dump}`.\n\n"
        "## Why\n\n"
        "The reduction must run before the fork so the downstream dump never "
        "sees uncompressed frames; compressing later would double the memory "
        "footprint of every frame that crosses the boundary.\n"
    )
    _assert_flagged([_unit("fake-g", body)], "fake-g", "grounding")


# ── structure ────────────────────────────────────────────────────────────────


def test_missing_why_section_is_caught_by_structure():
    body = (
        "This module routes signals between the ingress transport and the "
        "egress dispatcher, keeping backpressure out of the model path and "
        "allowing the transport to stay stateless while the dispatcher owns "
        "policy decisions for every frame that crosses the boundary.\n\n"
        "## Interfaces\n\n"
        "The dispatch entry point is what callers touch.\n"
    )
    _assert_flagged([_unit("fake-s1", body)], "fake-s1", "structure")


def test_token_why_section_is_caught_by_structure():
    body = (
        "This module routes signals between the ingress transport and the "
        "egress dispatcher, keeping backpressure out of the model path and "
        "allowing the transport to stay stateless while the dispatcher owns "
        "policy decisions for every frame that crosses the boundary.\n\n"
        "## Why\n\n"
        "Keep it stable.\n"
    )
    _assert_flagged([_unit("fake-s2", body)], "fake-s2", "structure")


# ── substance ────────────────────────────────────────────────────────────────


def test_substance_floor_catches_a_unit_without_explanation():
    body = "## Why\n\nThis module routes signals and keeps things working."
    _assert_flagged([_unit("fake-p", body)], "fake-p", "substance")


# ── claim-binding ────────────────────────────────────────────────────────────


def test_stated_live_quantity_without_a_claim_is_caught():
    body = (
        "This module routes signals between the ingress transport and the "
        "egress dispatcher, and the fleet it serves currently spans 88 "
        "workspaces across every tier that routes through it.\n\n"
        "## Why\n\n"
        "The transport must never decide routing policy, so the boundary layer "
        "separates concerns that would otherwise fuse into one hot path; moving "
        "the decision into the dispatcher would couple the transport to model "
        "selection and break the stateless pipeline contract.\n"
    )
    _assert_flagged([_unit("fake-c", body)], "fake-c", "claim-binding")


def test_good_unit_passes_every_check():
    body = _good_body()
    q.reset_universe()
    report = q.assess([_unit("real-1", body)], REPO_ROOT)
    assert "real-1" in report.passing, [str(i) for i in report.issues]
    assert not any(i.unit_id == "real-1" for i in report.issues)
