"""Tests for the spine drift census — claims and doc path refs.

`test_pattern_claim_catches_*` guards against a claim restating the number it
checks (`equals: 65`), which would pass trivially. P0 A1 deleted the pin axis
this module used to also test (`PinHealth`/`pin_health`) — none left to test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.platform.wiki import claims as claims_mod
from portal.platform.wiki import drift as drift_mod
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unit(uid: str, body: str, unit_claims: list[dict] | None = None) -> KnowledgeUnit:
    return KnowledgeUnit(
        id=uid,
        kind="what",
        title=uid,
        sources=[SourceRef(type="code", path="config/portal.yaml")],
        body=body,
        claims=unit_claims or [],
    )


# ── schema round-trip ────────────────────────────────────────────────────────


def test_claims_survive_frontmatter_round_trip():
    """`to_frontmatter` builds a fixed dict, so a key it omits is destroyed the
    next time save_unit() rewrites the file. Claims must be in that dict."""
    unit = _unit("u1", "body", [{"probe": "workspaces.total", "pattern": "{value} total"}])
    restored = KnowledgeUnit.from_markdown(unit.to_markdown())
    assert restored.claims == unit.claims


def test_unit_without_claims_round_trips_to_empty_list():
    unit = _unit("u2", "body")
    assert KnowledgeUnit.from_markdown(unit.to_markdown()).claims == []


# ── probes ───────────────────────────────────────────────────────────────────


def test_every_probe_returns_a_value_on_this_repo():
    results = claims_mod.probe_all(REPO_ROOT)
    assert set(results) == set(claims_mod.PROBES)
    broken = {k: v for k, v in results.items() if isinstance(v, str) and v.startswith("<error:")}
    assert not broken, f"probes failed: {broken}"


def test_workspace_probes_are_internally_consistent():
    total = claims_mod.probe("workspaces.total", REPO_ROOT)
    bench = claims_mod.probe("workspaces.bench", REPO_ROOT)
    functional = claims_mod.probe("workspaces.functional", REPO_ROOT)
    assert total == bench + functional
    assert total > 0


def test_unknown_probe_raises_rather_than_passing_quietly():
    with pytest.raises(KeyError):
        claims_mod.probe("no.such.probe", REPO_ROOT)


def test_workspace_names_returns_ids_not_display_labels():
    """`workspaces` is a mapping id -> spec and `name` inside it is a display
    label. Reading `name` would zero the bench count, since that is a prefix
    match on the id."""
    names = claims_mod._workspace_names(REPO_ROOT)
    assert any(n.startswith("bench-") for n in names)
    assert not any(n.startswith(("\U0001f916", "\U0001f513")) for n in names)


def test_workspace_names_rejects_an_unexpected_config_shape(tmp_path):
    """A future restructure to a list of dicts must fail loudly. The previous
    implementation would have silently returned display labels instead."""
    import yaml

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "portal.yaml").write_text(
        yaml.dump({"workspaces": [{"name": "display only"}]}), encoding="utf-8"
    )
    with pytest.raises(TypeError, match="must be a mapping"):
        claims_mod._workspace_names(tmp_path)


# ── claim evaluation ─────────────────────────────────────────────────────────


def test_pattern_claim_holds_when_body_carries_live_value():
    live = claims_mod.probe("workspaces.total", REPO_ROOT)
    unit = _unit(
        "u3",
        f"Portal ships {live} workspaces today.",
        [{"probe": "workspaces.total", "pattern": "{value} workspaces"}],
    )
    assert claims_mod.evaluate_claims([unit], REPO_ROOT) == []


def test_pattern_claim_catches_a_body_that_fell_behind_code():
    live = claims_mod.probe("workspaces.total", REPO_ROOT)
    unit = _unit(
        "u4",
        f"Portal ships {live - 6} workspaces today.",
        [{"probe": "workspaces.total", "pattern": "{value} workspaces"}],
    )
    violations = claims_mod.evaluate_claims([unit], REPO_ROOT)
    assert len(violations) == 1
    assert violations[0].op == "pattern"
    assert str(live) in str(violations[0])


def test_pattern_without_value_placeholder_is_itself_a_violation():
    unit = _unit("u5", "anything", [{"probe": "workspaces.total", "pattern": "no placeholder"}])
    assert len(claims_mod.evaluate_claims([unit], REPO_ROOT)) == 1


def test_equals_claim_on_structural_invariant():
    live = claims_mod.probe("backends.types", REPO_ROOT)
    ok = _unit("u6", "", [{"probe": "backends.types", "equals": live}])
    bad = _unit("u7", "", [{"probe": "backends.types", "equals": ["ollama"]}])
    assert claims_mod.evaluate_claims([ok], REPO_ROOT) == []
    assert len(claims_mod.evaluate_claims([bad], REPO_ROOT)) == 1


def test_contains_claim():
    ok = _unit("u8", "", [{"probe": "backends.types", "contains": "ollama"}])
    bad = _unit("u9", "", [{"probe": "backends.types", "contains": "vllm"}])
    assert claims_mod.evaluate_claims([ok], REPO_ROOT) == []
    assert len(claims_mod.evaluate_claims([bad], REPO_ROOT)) == 1


def test_unknown_probe_in_frontmatter_is_a_violation_not_a_pass():
    unit = _unit("u10", "x", [{"probe": "workspaces.totl", "pattern": "{value}"}])
    assert len(claims_mod.evaluate_claims([unit], REPO_ROOT)) == 1


def test_claim_with_no_operator_is_a_violation():
    unit = _unit("u11", "x", [{"probe": "workspaces.total"}])
    assert len(claims_mod.evaluate_claims([unit], REPO_ROOT)) == 1


# ── doc path references ──────────────────────────────────────────────────────


def test_served_model_ids_are_not_treated_as_filesystem_paths():
    """`portal/auto-coding` is an OpenAI-style model id. The suppression is exact
    — checked against the live roster — so a retired workspace id still reports."""
    model_ids = drift_mod._served_model_ids(REPO_ROOT)
    live = claims_mod._workspace_names(REPO_ROOT)
    assert f"portal/{live[0]}" in model_ids
    assert "portal/auto-agentic-ornith" not in model_ids


def test_broken_path_refs_are_reported_as_doc_and_path():
    for ref in drift_mod.broken_path_refs(REPO_ROOT):
        doc, _, path = ref.partition("::")
        assert doc and path
        assert (REPO_ROOT / doc).exists()
        assert not (REPO_ROOT / path).exists()


# ── absolute drift gate (baseline retired in TASK_WIKI_ZERO_DEBT_V1) ─────────


def test_pin_axis_is_fully_removed():
    """P0 A1: no pin/phantom vocabulary survives anywhere in the module."""
    assert not hasattr(drift_mod, "pin_health")
    assert not hasattr(drift_mod, "PinHealth")
    unit = KnowledgeUnit(
        id="u16",
        kind="what",
        title="u16",
        sources=[SourceRef(type="doc", path="https://example.invalid/spec")],
        body="x",
    )
    assert not hasattr(unit, "last_generated_commit")


def test_census_is_read_only_and_self_consistent():
    before = drift_mod.broken_path_refs(REPO_ROOT)
    report = drift_mod.census(REPO_ROOT)
    assert report["units_total"] > 0
    assert "pins" not in report
    assert tuple(report["broken_path_refs"]) == before
    assert "ratchet" not in report and "retired" not in report


def test_undeclared_numeric_census_skips_units_that_declare_a_claim():
    plain = _unit("u17", "There are 12 workspaces here.")
    declared = _unit(
        "u18",
        "There are 12 workspaces here.",
        [{"probe": "workspaces.total", "pattern": "{value} workspaces"}],
    )
    found = drift_mod.undeclared_numeric_claims([plain, declared])
    assert "u17" in found and "u18" not in found


# ── P0 regression: BS-claims still HARD-FAILs a wrong declared number ────────


def test_bs_check_hard_fails_a_deliberately_wrong_declared_number(tmp_path, monkeypatch):
    """P0.2 exit criterion: BS still HARD-FAILs a wrong declared number
    with the pin axis gone — A2's anti-drift core is untouched by A1."""
    from portal.platform.wiki import store as store_mod
    from scripts.validation import wiki as wiki_checks

    live = claims_mod.probe("workspaces.total", REPO_ROOT)
    wrong = _unit(
        "unit-p0-regression-wrong-count",
        f"Portal ships {live + 1} workspaces today.",
        [{"probe": "workspaces.total", "pattern": "{value} workspaces"}],
    )

    canonical = tmp_path / "canonical"
    canonical.mkdir()
    store_mod.set_canonical_dir(canonical)
    monkeypatch.setattr(wiki_checks, "REPO_ROOT", REPO_ROOT)
    try:
        store_mod.save_unit(wrong)
        status, detail, _subs = wiki_checks.check_spine_drift()
    finally:
        store_mod.reset_canonical_dir()

    assert status == "FAIL", detail
    assert "unit-p0-regression-wrong-count" in detail or "claim violation" in detail


def test_bs_check_passes_when_declared_number_is_correct(tmp_path, monkeypatch):
    """Sibling check: a correct claim isn't penalized by the pin axis's removal."""
    from portal.platform.wiki import store as store_mod
    from scripts.validation import wiki as wiki_checks

    live = claims_mod.probe("workspaces.total", REPO_ROOT)
    right = _unit(
        "unit-p0-regression-right-count",
        f"Portal ships {live} workspaces today.",
        [{"probe": "workspaces.total", "pattern": "{value} workspaces"}],
    )

    canonical = tmp_path / "canonical"
    canonical.mkdir()
    store_mod.set_canonical_dir(canonical)
    monkeypatch.setattr(wiki_checks, "REPO_ROOT", REPO_ROOT)
    try:
        store_mod.save_unit(right)
        status, detail, _subs = wiki_checks.check_spine_drift()
    finally:
        store_mod.reset_canonical_dir()

    assert status == "PASS", detail


# ── P0 regression: a fact change regenerates + commits in one commit ────────


def test_fact_unit_regeneration_touches_no_pin_field(tmp_path, monkeypatch):
    """Exit criterion: a live-count re-derivation is single-commit — no pin
    field left to bump in a second commit."""
    from portal.platform.wiki import store as store_mod
    from portal.platform.wiki.adapters.seed_facts import derive_persona_roster

    canonical = tmp_path / "canonical"
    canonical.mkdir()
    store_mod.set_canonical_dir(canonical)
    try:
        unit = derive_persona_roster("deadbeef", save=True)
        on_disk = (canonical / f"{unit.id}.md").read_text(encoding="utf-8")
        assert "last_generated_commit" not in on_disk

        # Re-deriving with a *different* commit but unchanged live config must
        # produce a byte-identical file — there is nothing left that a mere
        # HEAD advance would need to re-stamp.
        before = on_disk
        derive_persona_roster("cafef00d", save=True)
        after = (canonical / f"{unit.id}.md").read_text(encoding="utf-8")
        assert before == after
    finally:
        store_mod.reset_canonical_dir()
