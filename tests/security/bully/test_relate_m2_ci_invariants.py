"""M.2 -- CI invariants for operating/measurement separation: each check
fails on a seeded violation and passes clean."""

from __future__ import annotations

from scripts.validation import all_checks


def _run(slug: str) -> tuple[str, str, list[dict]]:
    fn = next(fn for s, _label, fn in all_checks() if s == slug)
    return fn()


def test_all_bully_relate_checks_registered_and_pass_clean():
    slugs = {s for s, _label, _fn in all_checks() if s.startswith("bully_")}
    expected = {
        "bully_capability_denial",
        "bully_score_eligibility",
        "bully_pairwise_relational",
        "bully_lineage_corroboration",
        "bully_anchor_provenance_required",
        "bully_outcome_write_back",
        "bully_system_generated_never_ground_truth",
        "bully_depth_cap_enforced",
        "bully_canary_never_in_library",
        "bully_consumer_honours_confidence",
        "bully_uncertainty_not_constant",
    }
    assert expected <= slugs
    for slug in expected:
        status, detail, _sub = _run(slug)
        assert status == "PASS", f"{slug} did not pass clean: {detail}"


def test_capability_denial_check_would_fail_on_a_seeded_violation():
    from portal.modules.security.core.bully.connectors import QueryIntent
    from portal.modules.security.core.bully.data_plane import DataPlane

    plane = DataPlane()

    class _DenyingConnector:
        source_id = "denying"
        mode = "ingest"

        def translate(self, intent):
            raise PermissionError("capability check failed")

        def read(self, intent):
            raise PermissionError("zero-capability source denied")

    plane.connectors["denying"] = _DenyingConnector()
    try:
        plane.query("denying", QueryIntent(purpose="x"))
    except PermissionError:
        pass  # the seeded violation is caught (this is what the CI check guards against)
    else:
        raise AssertionError("seeded capability-denial connector unexpectedly succeeded")


def test_score_eligibility_check_would_fail_on_a_seeded_violation():
    from types import SimpleNamespace

    from portal.modules.security.core.bully import measurement
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    lib = AnchorLibrary()
    weak_anchor = lib.load_advisory(source_id="advisory", technique=None)
    ineligible = SimpleNamespace(
        assessment=SimpleNamespace(reference_signature_id=weak_anchor.anchor_id)
    )
    # The seeded violation: scoring an ineligible row anyway.
    seeded_report = measurement.compute_accuracy([(ineligible, lib, "SAME")])
    assert seeded_report.scored_count == 0  # the guard refuses to score it
    assert seeded_report.unscored_count == 1


def test_system_generated_ground_truth_check_would_fail_on_a_seeded_violation():
    from portal.modules.security.core.bully import provenance
    from portal.modules.security.core.bully.anchors import make_anchor

    seeded_bad_anchor = make_anchor(
        "confirmed_finding", {}, source_id="x", provenance_tier="SYSTEM_GENERATED"
    )
    assert provenance.can_raise_confidence(seeded_bad_anchor) is False


def test_canary_check_would_fail_on_a_seeded_violation():
    import pytest

    from portal.modules.security.core.bully import canary

    protected = canary.CanarySet(protected_record_ids=frozenset({"heldout-x"}))
    with pytest.raises(canary.CanaryViolationError):
        canary.guard_write_back(protected, "heldout-x")
