"""Bully relation+investigation family checks (BY-CI): the M.2 executable
grounding for TASK_BULLY_RELATE_AND_INVESTIGATE_V1 -- each check seeds a
violation and confirms the guard rejects it, then confirms a clean input
still passes. This keeps the operating/measurement discipline in the repo
instead of in task prose."""

from __future__ import annotations

from types import SimpleNamespace

from .registry import register


@register("bully_capability_denial", "BY. capability status never denies a read", order=74)
def check_capability_never_denies_read() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.connectors import IterableIngestConnector, QueryIntent
    from portal.modules.security.core.bully.data_plane import CAPABILITIES, DataPlane

    plane = DataPlane()
    connector = IterableIngestConnector("zero-cap", [{"v": 1}])
    plane.connect(
        "zero-cap",
        connector,
        connector.records,
        source_meta={"capabilities": dict.fromkeys(CAPABILITIES, False)},
    )
    try:
        result = plane.query("zero-cap", QueryIntent(purpose="x"))
    except Exception as e:
        return "FAIL", f"zero-capability source read was denied: {e}", []
    if len(result.records) != 1:
        return "FAIL", "zero-capability source read returned no records", []
    return "PASS", "", []


@register("bully_score_eligibility", "BZ. score never claimed without eligibility", order=75)
def check_score_requires_eligibility() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import measurement
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    lib = AnchorLibrary()
    weak_anchor = lib.load_advisory(source_id="advisory", technique=None)  # no label basis -> weak
    ineligible = SimpleNamespace(
        assessment=SimpleNamespace(reference_signature_id=weak_anchor.anchor_id)
    )
    if measurement.score_eligible(ineligible, lib):
        return "FAIL", "a weak, label-less anchor match was treated as score-eligible", []

    strong_anchor = lib.load_attack_episode(
        source_id="attack_data", record={}, techniques=("T1059",)
    )
    eligible = SimpleNamespace(
        assessment=SimpleNamespace(reference_signature_id=strong_anchor.anchor_id)
    )
    if not measurement.score_eligible(eligible, lib):
        return "FAIL", "a strong, EXTERNAL anchor match was denied score-eligibility", []
    return "PASS", "", []


@register(
    "bully_pairwise_relational", "CA. relational properties are pairwise, not per-source", order=76
)
def check_relational_properties_pairwise() -> tuple[str, str, list[dict]]:
    import inspect

    from portal.modules.security.core.bully import measurement
    from portal.modules.security.core.bully.data_plane import CapabilityProfile

    if len(inspect.signature(measurement.pairwise_timeline_comparable).parameters) != 2:
        return "FAIL", "pairwise_timeline_comparable is not a two-source function", []
    if len(inspect.signature(measurement.pairwise_entity_linkable).parameters) != 2:
        return "FAIL", "pairwise_entity_linkable is not a two-source function", []
    leaked = {"timeline_comparable", "entity_linkable"} & set(
        CapabilityProfile.__dataclass_fields__
    )
    if leaked:
        return "FAIL", f"relational property stored per-source on CapabilityProfile: {leaked}", []
    return "PASS", "", []


@register("bully_lineage_corroboration", "CB. lineage prevents cross-corroboration", order=77)
def check_lineage_prevents_corroboration() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import measurement

    groups = measurement.LineageGroups(groups={"a": "shared", "b": "shared"})
    if measurement.corroboration_count(groups, ["a", "b"]) != 1:
        return "FAIL", "two sources in one lineage set corroborated independently", []
    if measurement.corroboration_count(groups, ["a", "c"]) != 2:
        return "FAIL", "independent sources were incorrectly collapsed", []
    return "PASS", "", []


@register(
    "bully_anchor_provenance_required", "CC. anchor never asserted without provenance", order=78
)
def check_anchor_requires_provenance() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.anchors import PROVENANCE_TIERS, make_anchor

    anchor = make_anchor("advisory", {}, source_id="x")
    if anchor.provenance_tier not in PROVENANCE_TIERS:
        return "FAIL", "anchor created without a valid provenance tier", []
    try:
        make_anchor("advisory", {}, source_id="x", provenance_tier="MADE_UP_TIER")
    except ValueError:
        pass
    else:
        return "FAIL", "an anchor with an unrecognised provenance tier was accepted", []
    return "PASS", "", []


@register("bully_outcome_write_back", "CD. every outcome is written back as an anchor", order=79)
def check_outcome_always_written_back() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import compounding
    from portal.modules.security.core.bully import signatures as sig_mod
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    lib = AnchorLibrary()
    signature = sig_mod.build_signature({"target_host": "h"}, {})
    for outcome in ("BENIGN_CLOSE", "ESCALATE", "RESPOND", "ANOMALOUS_UNCLASSIFIED"):
        anchor = compounding.write_outcome_as_anchor(
            lib, signature, source_id="ci-check", outcome=outcome, analyst_confirmed=False
        )
        if anchor not in lib.all():
            return "FAIL", f"outcome {outcome} was not written back as an anchor", []
    if len(lib) != 4:
        return "FAIL", "not every outcome kind produced its own anchor", []
    return "PASS", "", []


@register(
    "bully_system_generated_never_ground_truth",
    "CE. SYSTEM_GENERATED never scores or raises confidence",
    order=80,
)
def check_system_generated_never_ground_truth() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import measurement, provenance
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    lib = AnchorLibrary()
    unreviewed = lib.load_confirmed_finding(
        source_id="x", record={}, outcome="ESCALATE", analyst_confirmed=False
    )
    if provenance.can_raise_confidence(unreviewed):
        return "FAIL", "a SYSTEM_GENERATED anchor was allowed to raise confidence", []
    fake_relation = SimpleNamespace(
        assessment=SimpleNamespace(reference_signature_id=unreviewed.anchor_id)
    )
    if measurement.score_eligible(fake_relation, lib):
        return "FAIL", "a SYSTEM_GENERATED anchor entered scoring ground truth", []
    return "PASS", "", []


@register("bully_depth_cap_enforced", "CF. anchor generation depth cap enforced", order=81)
def check_depth_cap_enforced() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import provenance
    from portal.modules.security.core.bully.anchors import make_anchor

    beyond_cap = make_anchor(
        "confirmed_finding",
        {},
        source_id="x",
        label_basis="analyst_decision",
        provenance_tier="ANALYST_CONFIRMED",
        generation_depth=provenance.MAX_GENERATION_DEPTH + 1,
    )
    if provenance.can_raise_confidence(beyond_cap):
        return "FAIL", "an anchor beyond the generation depth cap still raised confidence", []
    return "PASS", "", []


@register(
    "bully_canary_never_in_library",
    "CG. held-out canary set never appears in the anchor library",
    order=82,
)
def check_canary_never_written_back() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import canary

    protected = canary.CanarySet(protected_record_ids=frozenset({"heldout-1"}))
    try:
        canary.guard_write_back(protected, "heldout-1")
    except canary.CanaryViolationError:
        pass
    else:
        return "FAIL", "a held-out canary record was allowed to write back as an anchor", []
    return "PASS", "", []


@register(
    "bully_consumer_honours_confidence",
    "CH. a consumer ignoring relation confidence is rejected",
    order=83,
)
def check_consumer_honours_confidence() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import calibration

    ignoring_confidence = calibration.gate_escalation(0.1, has_independent_evidence=True)
    if ignoring_confidence.allowed:
        return "FAIL", "escalation below the confidence threshold was allowed", []
    honouring_both = calibration.gate_escalation(0.9, has_independent_evidence=True)
    if not honouring_both.allowed:
        return "FAIL", "escalation with confidence and evidence was incorrectly rejected", []
    return "PASS", "", []


@register(
    "bully_uncertainty_not_constant",
    "CI. uncertainty_reasons is never constant across inputs",
    order=84,
)
def check_uncertainty_reasons_vary() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import degeneracy

    constant = [
        SimpleNamespace(verdict="NEW", uncertainty_reasons=("thin_anchor_coverage:0_candidates",))
        for _ in range(10)
    ]
    report = degeneracy.check_uncertainty_variance(constant)
    if report.passes:
        return "FAIL", "a constant uncertainty_reasons set across 10 relations was not caught", []

    varying = [
        SimpleNamespace(verdict="NEW", uncertainty_reasons=(f"missing_dimension:axis-{i % 5}",))
        for i in range(10)
    ]
    report2 = degeneracy.check_uncertainty_variance(varying)
    if not report2.passes:
        return "FAIL", "genuinely varying uncertainty_reasons was incorrectly flagged", []
    return "PASS", "", []
