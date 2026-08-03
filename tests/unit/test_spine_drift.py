"""Tests for the spine drift census — claims, pin health, and doc path refs.

The design error these tests exist to pin down: an earlier draft let a claim
restate the number it was checking (`equals: 65`), which compared the probe with
itself and passed while the doc body still said 60. `test_pattern_claim_catches_*`
is the regression guard for that — a claim must bind the *body text*, not a copy.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from portal.platform.wiki import claims as claims_mod
from portal.platform.wiki import drift as drift_mod
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unit(
    uid: str, body: str, unit_claims: list[dict] | None = None, pin: str = ""
) -> KnowledgeUnit:
    return KnowledgeUnit(
        id=uid,
        kind="what",
        title=uid,
        sources=[SourceRef(type="code", path="config/portal.yaml")],
        body=body,
        last_generated_commit=pin,
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


# ── pin health ───────────────────────────────────────────────────────────────


def test_phantom_pin_is_classified_separately_from_stale():
    """An unresolvable SHA is not merely old — nothing can ever be diffed against
    it. 461 units shipped pinned to 05e42ec2, absent from the whole history."""
    unit = _unit("u12", "x", pin="0" * 40)
    health = drift_mod.pin_health(REPO_ROOT, [unit])
    assert health.phantom == ("u12",)
    assert health.stale == () and health.fresh == ()


def test_unpinned_unit_is_classified_as_unpinned():
    health = drift_mod.pin_health(REPO_ROOT, [_unit("u13", "x")])
    assert health.unpinned == ("u13",)


def test_pin_at_head_is_fresh_and_an_older_pin_is_stale():
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert drift_mod.pin_health(REPO_ROOT, [_unit("u14", "x", pin=head)]).fresh == ("u14",)

    first_change = subprocess.run(
        ["git", "log", "-2", "--format=%H", "--", "config/portal.yaml"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if len(first_change) < 2:
        pytest.skip("config/portal.yaml has fewer than two commits in this clone")
    assert drift_mod.pin_health(REPO_ROOT, [_unit("u15", "x", pin=first_change[1])]).stale == (
        "u15",
    )


def test_unit_citing_no_repo_local_path_is_not_classified():
    unit = KnowledgeUnit(
        id="u16",
        kind="what",
        title="u16",
        sources=[SourceRef(type="doc", path="https://example.invalid/spec")],
        body="x",
    )
    assert drift_mod.pin_health(REPO_ROOT, [unit]).total == 0


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


# ── ratchet ──────────────────────────────────────────────────────────────────


def test_baseline_round_trips_and_ratchet_is_clean_against_itself(tmp_path):
    health = drift_mod.pin_health(REPO_ROOT)
    refs = drift_mod.broken_path_refs(REPO_ROOT)
    rendered = drift_mod.render_baseline(health, refs)

    import yaml

    parsed = yaml.safe_load(rendered)
    assert parsed["phantom_pin_count"] == len(health.phantom)
    assert parsed["broken_ref_count"] == len(refs)

    (tmp_path / "config").mkdir()
    (tmp_path / drift_mod.BASELINE_RELPATH).write_text(rendered, encoding="utf-8")
    loaded = drift_mod.load_baseline(tmp_path)
    assert loaded["phantom_pins"] == frozenset(health.phantom)
    assert loaded["broken_refs"] == frozenset(refs)

    violations = drift_mod.ratchet_violations(health, refs, tmp_path)
    assert not any(violations.values()), "a freshly pinned baseline must report no drift"


def test_ratchet_fails_on_a_finding_absent_from_the_baseline(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / drift_mod.BASELINE_RELPATH).write_text(
        "phantom_pins: []\nunpinned: []\nbroken_refs: []\n", encoding="utf-8"
    )
    health = drift_mod.PinHealth(phantom=("new-unit",))
    violations = drift_mod.ratchet_violations(health, ("README.md::nope/gone.py",), tmp_path)
    assert violations["phantom_pins"] == ("new-unit",)
    assert violations["broken_refs"] == ("README.md::nope/gone.py",)


def test_missing_baseline_makes_every_finding_a_violation(tmp_path):
    health = drift_mod.PinHealth(unpinned=("u",))
    assert drift_mod.ratchet_violations(health, (), tmp_path)["unpinned"] == ("u",)


def test_retired_entries_are_reported_so_debt_can_be_repinned(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / drift_mod.BASELINE_RELPATH).write_text(
        "phantom_pins:\n  - fixed-unit\nunpinned: []\nbroken_refs: []\n", encoding="utf-8"
    )
    retired = drift_mod.retired_baseline_entries(drift_mod.PinHealth(), (), tmp_path)
    assert retired["phantom_pins"] == ("fixed-unit",)


# ── census ───────────────────────────────────────────────────────────────────


def test_census_is_read_only_and_self_consistent():
    before = drift_mod.broken_path_refs(REPO_ROOT)
    report = drift_mod.census(REPO_ROOT)
    assert report["units_total"] > 0
    assert report["pins"]["total"] == sum(
        report["pins"][k] for k in ("fresh", "stale", "phantom", "unpinned")
    )
    assert tuple(report["broken_path_refs"]) == before


def test_undeclared_numeric_census_skips_units_that_declare_a_claim():
    plain = _unit("u17", "There are 12 workspaces here.")
    declared = _unit(
        "u18",
        "There are 12 workspaces here.",
        [{"probe": "workspaces.total", "pattern": "{value} workspaces"}],
    )
    found = drift_mod.undeclared_numeric_claims([plain, declared])
    assert "u17" in found and "u18" not in found
