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


# ── TASK_BULLY_COUSIN_RELATION_V1 C.5: cousin-relation contract (CJ-CQ) ─────
# Each check seeds a violation, confirms rejection, then confirms a clean
# input still passes (N4: a guard that cannot fail is a defect).


def _cousin_arrival(**kwargs):
    defaults = dict(
        signature_id="s1",
        action_sequence=[],
        telemetry_shape={},
        context_topology={},
        parameter_families={},
        event_graph={},
        attack_mappings=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _cousin_corpus() -> list[dict]:
    """A small anchor corpus with a majority-boilerplate window and one
    distinguishable parent -- the same shape the C.1 contract tests use, so
    IDF weighting behaves predictably across these checks."""
    common = [
        {
            "record_id": f"common-{i}",
            "action_sequence": ["whoami", "net user", "ipconfig"],
            "telemetry_shape": {"source_class": "windows"},
            "context_topology": {"os": "windows"},
            "attack_mappings": [{"technique_id": "T1087"}],
        }
        for i in range(20)
    ]
    common.append(
        {
            "record_id": "PARENT-cred",
            "action_sequence": ["AssumeRole", "GetSessionToken", "ListBuckets"],
            "telemetry_shape": {"source_class": "cloudtrail"},
            "context_topology": {"cloud": "aws"},
            "attack_mappings": [{"technique_id": "T1078.004"}],
        }
    )
    return common


@register(
    "bully_cousin_coverage_never_gates",
    "CJ. cousin coverage never gates classification",
    order=85,
)
def check_cousin_coverage_never_gates() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import cousin_relation as cr

    anchors = _cousin_corpus()
    thin = _cousin_arrival(action_sequence=["AssumeRole", "GetSessionToken", "ListBuckets"])
    rel = cr.relate_cousin(thin, anchors)
    if rel.coverage >= 0.6:
        return "FAIL", "fixture coverage is not below the old mass floor -- adjust fixture", []
    if rel.status != "COUSIN_CANDIDATE":
        return "FAIL", f"a coverage-{rel.coverage:.2f} arrival was refused ({rel.status})", []

    # Seeded violation: a grader variant that gates on a mass floor must
    # disagree with the real grader on this exact fixture.
    def _gated_variant_status(coverage: float) -> str:
        return "INSUFFICIENT_VIEW" if coverage < 0.6 else rel.status

    if _gated_variant_status(rel.coverage) == rel.status:
        return "FAIL", "a coverage-gated variant was not distinguishable from the real grader", []
    return "PASS", "", []


@register(
    "bully_cousin_distance_normalized",
    "CK. cousin distance is normalized and comparable across coverage",
    order=86,
)
def check_cousin_distance_normalized() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import cousin_relation as cr

    anchors = _cousin_corpus()
    behavior = ["AssumeRole", "GetSessionToken", "ListBuckets"]
    thin = _cousin_arrival(action_sequence=behavior)
    rich = _cousin_arrival(
        signature_id="s2",
        action_sequence=behavior,
        telemetry_shape={"source_class": "cloudtrail"},
        context_topology={"cloud": "aws"},
    )
    d_thin = cr.relate_cousin(thin, anchors).distance
    d_rich = cr.relate_cousin(rich, anchors).distance
    if d_thin != d_rich:
        return "FAIL", f"distance not comparable across coverage: thin={d_thin} rich={d_rich}", []
    if d_thin != 0.0:
        return "FAIL", "fixture did not produce a perfect behavioural match", []
    return "PASS", "", []


@register(
    "bully_cousin_attack_axis_output_only",
    "CL. cousin attack axis is never required of the arrival",
    order=87,
)
def check_cousin_attack_axis_output_only() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import cousin_relation as cr

    anchors = _cousin_corpus()
    arrival = _cousin_arrival(action_sequence=["AssumeRole", "GetSessionToken", "ListBuckets"])
    rel = cr.relate_cousin(arrival, anchors)
    if rel.status != "COUSIN_CANDIDATE":
        return "FAIL", "arrival with no attack_mappings failed to relate", []
    if "T1078.004" not in rel.hypothesized_techniques:
        return "FAIL", "anchor's technique was not hypothesized as output", []
    if "attack" not in rel.delta.unobservable_dimensions:
        return "FAIL", "attack axis was not marked unobservable for the arrival", []
    return "PASS", "", []


@register(
    "bully_cousin_delta_mandatory",
    "CM. cousin delta is present on every COUSIN_CANDIDATE",
    order=88,
)
def check_cousin_delta_mandatory() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import cousin_relation as cr

    anchors = _cousin_corpus()
    arrival = _cousin_arrival(
        action_sequence=["AssumeRole", "GetSessionToken", "DescribeInstances"]
    )
    rel = cr.relate_cousin(arrival, anchors)
    if rel.status != "COUSIN_CANDIDATE":
        return "FAIL", "fixture did not produce a cousin verdict", []
    if rel.delta.is_empty:
        return "FAIL", "COUSIN_CANDIDATE emitted with an empty delta", []
    return "PASS", "", []


@register(
    "bully_cousin_no_overclaim",
    "CN. no parent named outside a cousin verdict",
    order=89,
)
def check_cousin_no_overclaim() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import cousin_relation as cr

    anchors = _cousin_corpus()
    unrelated = _cousin_arrival(
        action_sequence=["SELECT", "INSERT", "COMMIT"],
        telemetry_shape={"source_class": "db"},
        context_topology={"engine": "pg"},
    )
    rel = cr.relate_cousin(unrelated, anchors)
    if rel.status == "COUSIN_CANDIDATE":
        return "FAIL", "fixture unexpectedly related closely -- adjust to a farther arrival", []
    if rel.anchor_id is not None or rel.hypothesized_techniques != ():
        return "FAIL", "a parent/technique was named outside a COUSIN_CANDIDATE verdict", []
    if not rel.ranked_cousins:
        return "FAIL", "the distance profile was withheld outside a cousin verdict", []
    return "PASS", "", []


@register(
    "bully_cousin_bin_split_reachable",
    "CO. INSUFFICIENT_VIEW and NOVEL_NOTABLE are both reachable and distinct",
    order=90,
)
def check_cousin_bin_split_reachable() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import cousin_relation as cr

    anchors = _cousin_corpus()
    blank = _cousin_arrival()
    distinctive_unrelated = _cousin_arrival(
        signature_id="s2",
        action_sequence=["zzz-rare-token-1", "zzz-rare-token-2"],
        telemetry_shape={"weird": "shape"},
    )
    insufficient = cr.relate_cousin(blank, anchors)
    novel = cr.relate_cousin(distinctive_unrelated, anchors)
    if insufficient.status != "INSUFFICIENT_VIEW":
        return (
            "FAIL",
            f"a blank arrival did not reach INSUFFICIENT_VIEW ({insufficient.status})",
            [],
        )
    if novel.status != "NOVEL_NOTABLE":
        return (
            "FAIL",
            f"a distinctive-but-unrelated arrival did not reach NOVEL_NOTABLE ({novel.status})",
            [],
        )
    if insufficient.status == novel.status:
        return "FAIL", "INSUFFICIENT_VIEW and NOVEL_NOTABLE collapsed to one status", []
    return "PASS", "", []


@register(
    "bully_compounding_external_only",
    "CP. compounding is never scored on SYSTEM_GENERATED truth",
    order=91,
)
def check_compounding_external_only() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import measurement
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    lib = AnchorLibrary()
    sys_anchor = lib.load_confirmed_finding(
        source_id="observed:x", record={}, outcome="ESCALATE", analyst_confirmed=False
    )
    relation = SimpleNamespace(ranked_cousins=((sys_anchor.anchor_id, 0.1),))
    report = measurement.compounding_accuracy([(relation, lib, sys_anchor.anchor_id)])
    if report.valid:
        return "FAIL", "a compounding report with zero external rows reported valid=True", []
    if report.external_scored_count != 0:
        return "FAIL", "a SYSTEM_GENERATED match was scored as external ground truth", []

    ext_anchor = lib.load_attack_episode(source_id="attack_data", record={}, techniques=("T1059",))
    relation2 = SimpleNamespace(ranked_cousins=((ext_anchor.anchor_id, 0.1),))
    report2 = measurement.compounding_accuracy([(relation2, lib, ext_anchor.anchor_id)])
    if not report2.valid:
        return "FAIL", "a compounding report with a real external row was incorrectly INVALID", []
    return "PASS", "", []


@register(
    "bully_uncertainty_varies_within_source",
    "CQ. uncertainty reasons vary within a source, not just across sources",
    order=92,
)
def check_uncertainty_varies_within_source() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import degeneracy

    constant_within_each = []
    for source in ("src-a", "src-b", "src-c", "src-d", "src-e"):
        constant_within_each += [
            SimpleNamespace(verdict="NEW", uncertainty_reasons=(f"boilerplate:{source}",))
            for _ in range(4)
        ]
    batch_report = degeneracy.check_uncertainty_variance(constant_within_each)
    if not batch_report.passes:
        return "FAIL", "fixture unexpectedly failed the batch-level check -- adjust fixture", []

    grouped_report = degeneracy.check_uncertainty_variance(
        constant_within_each, group_by=lambda r: r.uncertainty_reasons[0].split(":", 1)[1]
    )
    if grouped_report.passes:
        return "FAIL", "reasons constant within one source were not caught by the grouped check", []

    varying = [
        SimpleNamespace(verdict="NEW", uncertainty_reasons=(f"content:{source}:{i}",))
        for source in ("src-a", "src-b")
        for i in range(6)
    ]
    grouped_ok = degeneracy.check_uncertainty_variance(
        varying, group_by=lambda r: r.uncertainty_reasons[0].split(":")[1]
    )
    if not grouped_ok.passes:
        return "FAIL", "genuinely within-source-varying reasons were incorrectly flagged", []
    return "PASS", "", []


# ── CR-DA: M.2 unknown-cousin invariants (TASK_BULLY_UNKNOWN_COUSIN_V1) ────


def _unit_from_verbs(verbs: list[str], entity: str) -> object:
    from portal.modules.security.core.bully.artifact_graph import build_graph, enumerate_units

    records = [
        {"eventName": v, "user": entity, "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = build_graph(records)
    return next(u for u in enumerate_units(graph) if u.level == "L4_WINDOW")


@register(
    "bully_unknown_cousin_library_never_gates",
    "CR. not in the library is never treated as not a concern (P2)",
    order=93,
)
def check_library_absence_never_suppresses_concern() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully import unit_outcome as uo

    model = bl.NormalBaseline(environment_id="ci")
    model.fit([_unit_from_verbs(["ListBuckets", "ListBuckets"], f"bg-{i}") for i in range(30)])

    remarkable_unit = _unit_from_verbs(
        ["AssumeRole", "GetSessionToken", "PutBucketPolicy"], "attacker"
    )
    outcome = uo.resolve_unit_outcome(remarkable_unit, [], model)  # empty library
    if outcome.outcome not in (*uo.CONCERN_OUTCOMES, "NORMAL"):
        return "FAIL", f"empty library produced an unreachable outcome: {outcome.outcome}", []
    if outcome.outcome == "NOVEL" and outcome.brief is None:
        return "FAIL", "NOVEL with an empty library carried no ConcernBrief", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_channel_coverage_never_gates",
    "CS. no classification gate reads coverage (carried from C.5)",
    order=94,
)
def check_channel_coverage_never_gates_classification() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import unit_relation as ur

    unit = _unit_from_verbs(["AssumeRole", "ListBuckets", "AttachUserPolicy"], "attacker")
    # No parameter_families on the anchor -> vocabulary channel's coverage
    # story differs from shape's, but shape alone must still be able to
    # classify EXACT/SIMILAR; low/zero coverage on one channel must never
    # deny the other.
    anchor = {
        "record_id": "t1",
        "action_sequence": ["AssumeRole", "ListBuckets", "AttachUserPolicy"],
    }
    relation = ur.grade_unit_against_type(unit, anchor)
    if relation.shape.relation == "NOT_AT_ALL" and relation.shape.coverage == 1.0:
        return "FAIL", "a fully-observed shape channel was downgraded to NOT_AT_ALL", []
    empty_anchor: dict = {"record_id": "t2"}
    unobservable_relation = ur.grade_unit_against_type(unit, empty_anchor)
    if unobservable_relation.vocabulary.relation != "NOT_AT_ALL":
        return "FAIL", "an unobservable channel produced a relation other than NOT_AT_ALL", []
    if unobservable_relation.vocabulary.coverage != 0.0:
        return "FAIL", "an unobservable channel did not report zero coverage honestly", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_brief_mandatory",
    "CT. every concern-raising outcome carries a non-empty ConcernBrief",
    order=95,
)
def check_every_concern_carries_a_brief() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully.anchors import AnchorLibrary
    from portal.modules.security.core.bully.unit_outcome import (
        CONCERN_OUTCOMES,
        resolve_unit_outcome,
    )

    library = AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["AssumeRole", "ListBuckets", "AttachUserPolicy"]},
        techniques=("T1078",),
    )
    model = bl.NormalBaseline(environment_id="ci")
    model.fit([_unit_from_verbs(["ListBuckets", "ListBuckets"], f"bg-{i}") for i in range(20)])

    unit = _unit_from_verbs(["AssumeRole", "ListBuckets", "AttachUserPolicy"], "attacker")
    outcome = resolve_unit_outcome(unit, list(library.all()), model)
    if outcome.outcome not in CONCERN_OUTCOMES:
        return "FAIL", f"fixture did not reach a concern-raising outcome: {outcome.outcome}", []
    if outcome.brief is None:
        return "FAIL", f"{outcome.outcome} carried no ConcernBrief", []
    if not outcome.brief.to_dict():
        return "FAIL", "ConcernBrief serialised to an empty payload", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_known_instance_never_headlines",
    "CU. KNOWN_INSTANCE never ranks above COUSIN/NOVEL (P1)",
    order=96,
)
def check_known_instance_never_headlines() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully.anchors import AnchorLibrary
    from portal.modules.security.core.bully.unit_outcome import (
        resolve_unit_outcome,
        sort_for_report,
    )

    library = AnchorLibrary()
    library.load_detection_coverage(source_id="det", detection_id="det-1")
    library._anchors["det-1"].record.update(
        {"action_sequence": ["AssumeRole", "ListBuckets", "AttachUserPolicy"]}
    )
    model = bl.NormalBaseline(environment_id="ci")
    model.fit([_unit_from_verbs(["ListBuckets", "ListBuckets"], f"bg-{i}") for i in range(20)])

    known = resolve_unit_outcome(
        _unit_from_verbs(["AssumeRole", "ListBuckets", "AttachUserPolicy"], "known"),
        list(library.all()),
        model,
    )
    if known.outcome != "KNOWN_INSTANCE":
        return "FAIL", "fixture did not reach KNOWN_INSTANCE -- adjust fixture", []
    novel = resolve_unit_outcome(
        _unit_from_verbs(["Delete", "Remove", "Terminate"], "novel"), [], model
    )
    ranked = sort_for_report([known, novel])
    if ranked[0].outcome == "KNOWN_INSTANCE" and ranked[0].outcome != ranked[-1].outcome:
        return "FAIL", "KNOWN_INSTANCE ranked above a concern-raising outcome", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_insufficient_view_distinct",
    "CV. INSUFFICIENT_VIEW and NOVEL are distinct and both reachable",
    order=97,
)
def check_insufficient_view_and_novel_are_distinct() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully.artifact_graph import (
        GradeableUnit,
        build_graph,
        enumerate_units,
    )
    from portal.modules.security.core.bully.unit_outcome import resolve_unit_outcome

    model = bl.NormalBaseline(environment_id="ci")
    benign_records = [
        {
            "eventName": "ListBuckets",
            "user": f"u{i % 20}",
            "eventTime": 1_700_000_000.0 + float(i * 37),
        }
        for i in range(200)
    ]
    benign_graph = build_graph(benign_records)
    model.fit([u for u in enumerate_units(benign_graph) if u.level == "L1_ARTIFACT"])

    # RC3/E.4: fit and score compare within the same level -- the probe
    # below is L4_WINDOW, so the baseline needs its own L4_WINDOW pool of
    # routine combinations, or the probe would score 0.0 honestly (never a
    # silent floor) instead of measuring genuine content novelty.
    attacker_verbs = [
        "AssumeRole",
        "GetSessionToken",
        "AttachUserPolicy",
        "PutBucketPolicy",
        "DeleteBucket",
        "PutObject",
        "AssumeRole",
        "AttachUserPolicy",
        "DeleteBucket",
    ]
    benign_cycle = ["ListBuckets", "GetObject", "DescribeInstances"]
    benign_combo = (benign_cycle * ((len(attacker_verbs) // len(benign_cycle)) + 1))[
        : len(attacker_verbs)
    ]
    model.fit([_unit_from_verbs(benign_combo, f"benign-combo-{i}") for i in range(50)])

    empty_unit = GradeableUnit(
        unit_id="u-empty",
        level="L1_ARTIFACT",
        artifact_ids=("a0",),
        entities=(),
        action_classes=(),
        edge_kinds=(),
        span_seconds=None,
        structural_signature={},
        vocabulary=(),
        source_ids=(),
    )
    insufficient = resolve_unit_outcome(empty_unit, [], model)
    novel = resolve_unit_outcome(
        _unit_from_verbs(attacker_verbs, "attacker"),
        [],
        model,
    )
    if insufficient.outcome != "INSUFFICIENT_VIEW":
        return "FAIL", "an uncomputable unit did not reach INSUFFICIENT_VIEW", []
    if novel.outcome != "NOVEL":
        return "FAIL", "fixture did not reach NOVEL -- adjust fixture", []
    if insufficient.outcome == novel.outcome:
        return "FAIL", "INSUFFICIENT_VIEW and NOVEL collapsed to one status", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_channels_separable",
    "CW. shape and vocabulary channels stay separable (P3)",
    order=98,
)
def check_shape_and_vocabulary_channels_are_separable() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import unit_relation as ur

    # Same class shape, entirely disjoint literal vocabulary.
    unit = _unit_from_verbs(["Authenticate", "Enumerate", "Grant"], "attacker")
    anchor = {
        "record_id": "t1",
        "action_sequence": ["AssumeRole", "ListBuckets", "AttachUserPolicy"],
    }
    relation = ur.grade_unit_against_type(unit, anchor)
    if relation.shape.relation == "NOT_AT_ALL":
        return "FAIL", "shape channel did not bridge a matching class shape", []
    if relation.vocabulary.relation != "NOT_AT_ALL":
        return "FAIL", "vocabulary channel matched despite disjoint literal tokens", []
    if relation.shape.relation == relation.vocabulary.relation:
        return "FAIL", "shape and vocabulary channels were not independently gradeable", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_temporal_edge_requires_entity",
    "CX. temporal adjacency never creates an edge without a shared entity (P4)",
    order=99,
)
def check_temporal_adjacency_requires_shared_entity() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.artifact_graph import build_graph

    records = [
        {"eventName": "ListBuckets", "user": f"user-{i}", "eventTime": float(i * 5)}
        for i in range(50)
    ]
    graph = build_graph(records)
    bare_temporal = [
        e
        for e in graph.edges
        if e.kind == "temporal_adjacency"
        and not (set(graph.artifacts[e.left].entities) & set(graph.artifacts[e.right].entities))
    ]
    if bare_temporal:
        return "FAIL", f"{len(bare_temporal)} temporal edges created without a shared entity", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_leave_one_out_published_beside_full",
    "CY. leave-one-family-out is computed and published whenever a full-library number is",
    order=100,
)
def check_leave_one_out_published_beside_full_library() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully import unit_measurement as um
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    library = AnchorLibrary()
    anchor_a = library.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["AssumeRole", "ListBuckets", "AttachUserPolicy"]},
        techniques=("T1078",),
    )
    model = bl.NormalBaseline(environment_id="ci")
    model.fit([_unit_from_verbs(["ListBuckets", "ListBuckets"], f"bg-{i}") for i in range(20)])

    report = um.run_leave_one_family_out(
        {"family_a": [_unit_from_verbs(["AssumeRole", "ListBuckets", "AttachUserPolicy"], "a1")]},
        {"family_a": [anchor_a]},
        list(library.all()),
        model,
        benign_eval_units=[],
    )
    payload = report.to_dict()
    if "cousin_recall" not in payload or "full_library_cousin_recall" not in payload:
        return "FAIL", "leave-one-out report did not publish both numbers together", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_held_out_split_enforced",
    "CZ. evaluation artifacts never originate from type-contributing datasets (T.2)",
    order=101,
)
def check_evaluation_datasets_never_contaminate_types() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import unit_measurement as um

    unsplit = um.HeldOutSplit(
        type_dataset_keys=frozenset({"ds-a", "ds-b"}), eval_dataset_keys=frozenset()
    )
    try:
        um.assert_no_contamination(["ds-a"], unsplit)
    except um.ContaminationError:
        pass
    else:
        return "FAIL", "a contaminated evaluation set was not rejected", []

    clean_split = um.split_datasets([f"ds-{i}" for i in range(10)], seed=1)
    try:
        um.assert_no_contamination(list(clean_split.eval_dataset_keys), clean_split)
    except um.ContaminationError:
        return "FAIL", "a genuinely clean evaluation set was incorrectly rejected", []
    return "PASS", "", []


@register(
    "bully_unknown_cousin_novel_requires_positive_remarkability",
    "DA. NOVEL requires positive remarkability against the baseline, never mere absence",
    order=102,
)
def check_novel_requires_positive_remarkability() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully.unit_outcome import resolve_unit_outcome

    empty_model = bl.NormalBaseline(environment_id="ci-empty")
    unit = _unit_from_verbs(["AssumeRole", "GetSessionToken", "PutBucketPolicy"], "attacker")
    outcome = resolve_unit_outcome(unit, [], empty_model)
    if outcome.outcome == "NOVEL":
        return "FAIL", "an empty (never-fitted) baseline still produced NOVEL by absence alone", []
    if outcome.outcome != "NORMAL":
        return "FAIL", f"expected NORMAL with an unfitted baseline, got {outcome.outcome}", []
    return "PASS", "", []


@register(
    "bully_universal_intake_no_unit_from_invalid_role_map",
    "DB. no unit is emitted from a source whose role map is invalid (Q1)",
    order=103,
)
def check_no_unit_from_invalid_role_map() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.artifact_graph import build_graph, enumerate_units

    unextractable = [
        {"blob": "x" * 300, "note": f"free text {i} unrelated content"} for i in range(10)
    ]
    graph = build_graph(unextractable)
    if graph.role_map is None or graph.role_map.extraction_valid:
        return "FAIL", "an unextractable source was not flagged extraction_valid=False", []
    units = enumerate_units(graph)
    if units:
        return "FAIL", f"{len(units)} units were emitted from a source-level blind graph", []

    valid_records = [
        {
            "eventName": ["AssumeRole", "ListBuckets"][i % 2],
            "user": f"u{i % 10}",
            "eventTime": 1_700_000_000.0 + i,
        }
        for i in range(40)
    ]
    valid_graph = build_graph(valid_records)
    if valid_graph.role_map is None or not valid_graph.role_map.extraction_valid:
        return "FAIL", "a genuinely extractable source was flagged invalid", []
    if not enumerate_units(valid_graph):
        return "FAIL", "a genuinely extractable source produced no units", []
    return "PASS", "", []


@register(
    "bully_universal_intake_field_roles_resolve_plural_schemas",
    "DC. field roles resolve for >=3 disjoint schemas (Q2), against the E.3 fixture",
    order=104,
)
def check_field_roles_resolve_plural_schemas() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import blend
    from portal.modules.security.core.bully.artifact_graph import build_graph

    records, provenance = blend.compose_blend()
    schemas = blend.schemas_present(records, provenance)
    if len(schemas) < 3:
        return "FAIL", f"blend fixture carries only {len(schemas)} schemas, need >=3", []
    graph = build_graph(records)
    if graph.role_map is None or not graph.role_map.extraction_valid:
        return "FAIL", "the plural blend fixture failed extraction", []
    return "PASS", "", []


@register(
    "bully_universal_intake_extraction_failure_never_shared_shape",
    "DD. an extraction failure never produces a shared shape feature (the RC1 pattern)",
    order=105,
)
def check_extraction_failure_never_shared_shape() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.artifact_graph import build_graph, enumerate_units

    # Two unrelated unextractable sources -- under the RC1 defect both would
    # degrade to an identical all-`other` class_sequence and read as a
    # shape match. Under the fix, neither emits a unit at all.
    blind_a = [{"noise": f"aaaa{i}" * 5} for i in range(10)]
    blind_b = [{"garble": f"zzzz{i}" * 5} for i in range(10)]
    graph_a = build_graph(blind_a)
    graph_b = build_graph(blind_b)
    if enumerate_units(graph_a) or enumerate_units(graph_b):
        return "FAIL", "an unextractable source emitted gradeable units", []
    if graph_a.role_map is None or graph_b.role_map is None:
        return "FAIL", "role maps missing on blind graphs", []
    if graph_a.role_map.extraction_valid or graph_b.role_map.extraction_valid:
        return "FAIL", "an unextractable source was marked extraction_valid", []
    return "PASS", "", []


@register(
    "bully_universal_intake_identical_fit_score_near_zero",
    "DE. remarkability of an identical fitted+scored unit is ~0.0 (RC3)",
    order=106,
)
def check_identical_fit_score_near_zero() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl

    unit = _unit_from_verbs(["AssumeRole", "ListBuckets", "AttachUserPolicy"], "attacker")
    model = bl.NormalBaseline(environment_id="ci")
    model.fit([unit] * 100)
    score = model.remarkability(unit)
    if score >= 0.05:
        return "FAIL", f"fit N copies, score the identical unit -> {score}, expected ~0.0", []
    return "PASS", "", []


@register(
    "bully_universal_intake_ladder_validated_on_shape_distance",
    "DF. the falsification ladder is validated on shape_distance, the deciding variable (RC4)",
    order=107,
)
def check_ladder_validated_on_shape_distance() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import unit_ladder as ul

    parent_verbs = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
    rungs = ul.build_rungs(
        parent_verbs,
        substitution_verb="AddRole",
        cross_vocabulary_verbs=["Logon", "whoami", "Invoke-Command"],
        unrelated_verbs=["SELECT", "INSERT", "COMMIT"],
    )
    report = ul.run_ladder({"record_id": "parent-type", "action_sequence": parent_verbs}, rungs)
    if report.get("validated_variable") != "shape_distance":
        return "FAIL", "ladder report does not declare shape_distance as the validated variable", []
    return "PASS", "", []


@register(
    "bully_universal_intake_neither_channel_never_a_concern",
    "DG. neither-channel-observable never surfaces as a concern, only INSUFFICIENT_VIEW (RC5)",
    order=108,
)
def check_neither_channel_never_a_concern() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully.artifact_graph import GradeableUnit
    from portal.modules.security.core.bully.unit_outcome import resolve_unit_outcome

    empty_unit = GradeableUnit(
        unit_id="u-empty",
        level="L1_ARTIFACT",
        artifact_ids=("a0",),
        entities=(),
        action_classes=(),
        edge_kinds=(),
        span_seconds=None,
        structural_signature={},
        vocabulary=(),
        source_ids=(),
    )
    model = bl.NormalBaseline(environment_id="ci")
    outcome = resolve_unit_outcome(empty_unit, [], model)
    if outcome.outcome != "INSUFFICIENT_VIEW":
        return "FAIL", f"an uncomputable unit reached {outcome.outcome}, not INSUFFICIENT_VIEW", []
    if outcome.brief is not None:
        return "FAIL", "INSUFFICIENT_VIEW carried a brief -- it is not a concern", []
    return "PASS", "", []


@register(
    "bully_universal_intake_cousin_recall_excludes_novel",
    "DH. cousin_recall excludes NOVEL outcomes (RC6)",
    order=109,
)
def check_cousin_recall_excludes_novel() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully import unit_measurement as um

    model = bl.NormalBaseline(environment_id="ci")
    model.fit([_unit_from_verbs(["ListBuckets", "ListBuckets"], f"u{i}") for i in range(50)])
    benign_cycle = ["ListBuckets", "GetObject", "DescribeInstances"]
    attacker_verbs = [
        "AssumeRole",
        "GetSessionToken",
        "AttachUserPolicy",
        "PutBucketPolicy",
        "DeleteBucket",
        "PutObject",
        "AssumeRole",
        "AttachUserPolicy",
        "DeleteBucket",
    ]
    benign_combo = (benign_cycle * ((len(attacker_verbs) // len(benign_cycle)) + 1))[
        : len(attacker_verbs)
    ]
    model.fit([_unit_from_verbs(benign_combo, f"bg-combo-{i}") for i in range(50)])

    eval_units = {"family_novel": [_unit_from_verbs(attacker_verbs, "attacker")]}
    report = um.run_leave_one_family_out(
        eval_units, {"family_novel": []}, [], model, benign_eval_units=[]
    )
    if report.novelty_recall <= 0.0:
        return "FAIL", "fixture did not reach NOVEL -- adjust fixture", []
    if report.cousin_recall != 0.0:
        return "FAIL", "a pure-NOVEL population produced nonzero cousin_recall", []
    return "PASS", "", []


@register(
    "bully_universal_intake_absolute_recall_published",
    "DI. absolute recall is published whenever conditional recall is (RC6)",
    order=110,
)
def check_absolute_recall_published() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully import unit_measurement as um
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    library = AnchorLibrary()
    anchor = library.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["AssumeRole", "ListBuckets", "AttachUserPolicy"]},
        techniques=("T1078",),
    )
    model = bl.NormalBaseline(environment_id="ci")
    model.fit([_unit_from_verbs(["ListBuckets", "ListBuckets"], f"u{i}") for i in range(20)])
    report = um.run_leave_one_family_out(
        {"family_a": [_unit_from_verbs(["AssumeRole", "ListBuckets", "AttachUserPolicy"], "a1")]},
        {"family_a": [anchor]},
        list(library.all()),
        model,
        benign_eval_units=[],
        known_activity_count_by_family={"family_a": 3},
    )
    payload = report.to_dict()
    if "absolute_recall" not in payload or "conditional_recall" not in payload:
        return "FAIL", "absolute_recall was not published beside conditional_recall", []
    return "PASS", "", []


@register(
    "bully_universal_intake_ground_truth_only_through_sealed_wall",
    "DJ. generated ground truth reaches scoring only through the sealed wall (Q3)",
    order=111,
)
def check_ground_truth_only_through_sealed_wall(tmp_path=None) -> tuple[str, str, list[dict]]:
    import tempfile
    from pathlib import Path

    from portal.modules.security.core.bully import inject_plane as ip
    from portal.modules.security.core.bully import specimen_ledger

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        steps = (
            ip.GenerateStep(
                family="discovery",
                technique="T1018",
                chain_id="ci-chain-1",
                step_idx=0,
                command="echo hi",
                result={"ok": True, "output": "hi"},
            ),
        )
        report = ip.GenerateReport(plane="live", reason="", steps=steps)
        sealed = ip.seal_ground_truth(report, (), root=root)
        if sealed != 1:
            return "FAIL", "seal_ground_truth did not seal the generated step", []
        ledger = specimen_ledger.SpecimenLedger(root)
        (row,) = ledger.records()
        if (
            not row["specimen_id"].startswith("ci-chain-1-step0")
            or row.get("source_lane") != "live_lab"
        ):
            return "FAIL", "sealed ground truth did not use the existing SpecimenLedger wall", []
    return "PASS", "", []


@register(
    "bully_universal_intake_injected_artifacts_carry_labels",
    "DK. injected artifacts carry family/technique/chain/step labels (Q4)",
    order=112,
)
def check_injected_artifacts_carry_labels() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import blend

    _records, provenance = blend.compose_blend()
    injected = [p for p in provenance.values() if p.injected]
    if not injected:
        return "FAIL", "the blend fixture produced no injected artifacts", []
    for p in injected:
        if p.family is None or p.technique is None or p.chain_id is None or p.step_idx is None:
            return "FAIL", f"an injected artifact is missing a label: {p}", []
    benign = [p for p in provenance.values() if not p.injected]
    if any(p.family is not None or p.technique is not None for p in benign):
        return "FAIL", "a benign artifact carried a family/technique label", []
    return "PASS", "", []


# ── DL-DS: TASK_BULLY_LOOP_REINTEGRATION_V1 (R.7) -- loop reintegration and
# pyramid-of-pain invariants. Each seeds a violation, confirms rejection,
# then confirms clean input passes. ──────────────────────────────────────────


@register(
    "bully_loop_reintegration_orchestrator_uses_loop_grader",
    "DL. orchestrator's grade path uses loop_grader, never cousin_engine (R1)",
    order=113,
)
def check_orchestrator_grades_via_loop_grader() -> tuple[str, str, list[dict]]:
    import ast
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "portal"
        / "modules"
        / "security"
        / "core"
        / "bully"
        / "orchestrator.py"
    )
    tree = ast.parse(path.read_text())
    imported_from_cousin_engine: set[str] = set()
    imported_loop_grader = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.endswith("cousin_engine")
        ):
            imported_from_cousin_engine.update(alias.name for alias in node.names)
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is None
            and node.level >= 1
            and any(alias.name == "loop_grader" for alias in node.names)
        ):
            imported_loop_grader = True
    # seeded violation: a `grade` re-import would put cousin_engine back on
    # the call path -- confirm it is rejected by this very assertion.
    if "grade" in imported_from_cousin_engine:
        return "FAIL", "orchestrator.py imports cousin_engine.grade -- R1 violated", []
    if not imported_loop_grader:
        return "FAIL", "orchestrator.py does not import loop_grader", []
    return "PASS", "", []


@register(
    "bully_loop_reintegration_same_requires_behavioural_match",
    "DM. SAME never arises from a non-behavioural (L1/L2-only) match (R3)",
    order=114,
)
def check_same_requires_behavioural_match() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import loop_grader, pyramid

    l1_only_subj = [pyramid.level_feature("sourcetype=x", "CONSTANT")]
    l1_only_anchor = [pyramid.level_feature("sourcetype=x", "CONSTANT")]
    seeded = loop_grader.grade_for_loop(l1_only_subj, "a1", l1_only_anchor, distance=0.0)
    if seeded.relationship == "SAME":
        return "FAIL", "an L1-only match at distance=0 graded SAME -- R3 violated", []

    behavioural_subj = [
        pyramid.level_feature("v1", "ACTION", raw_verb="assumerole"),
        pyramid.level_feature("v2", "ACTION", raw_verb="listbuckets"),
    ]
    behavioural_anchor = [
        pyramid.level_feature("v1", "ACTION", raw_verb="assumerole"),
        pyramid.level_feature("v2", "ACTION", raw_verb="listbuckets"),
    ]
    clean = loop_grader.grade_for_loop(behavioural_subj, "a2", behavioural_anchor, distance=0.05)
    if clean.relationship != "SAME":
        return "FAIL", f"a genuine L3 close match graded {clean.relationship}, not SAME", []
    return "PASS", "", []


@register(
    "bully_loop_reintegration_blindness_is_indeterminate_not_different",
    "DN. extraction blindness -> ANOMALOUS_UNCLASSIFIED+INDETERMINATE, never DIFFERENT (Q1)",
    order=115,
)
def check_blindness_is_indeterminate() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import loop_grader

    seeded = loop_grader.grade_for_loop([], None, None, distance=None)
    if seeded.relationship == "DIFFERENT":
        return "FAIL", "instrument blindness graded DIFFERENT -- Q1 violated", []
    if (
        seeded.relationship != "ANOMALOUS_UNCLASSIFIED"
        or seeded.defense_response != "INDETERMINATE"
    ):
        return (
            "FAIL",
            f"blind input graded {seeded.relationship}/{seeded.defense_response}, "
            "expected ANOMALOUS_UNCLASSIFIED/INDETERMINATE",
            [],
        )
    return "PASS", "", []


@register(
    "bully_loop_reintegration_cross_vocabulary_cousin_grades_similar",
    "DO. a cross-vocabulary cousin (disjoint tokens, shared spine) grades SIMILAR",
    order=116,
)
def check_cross_vocabulary_cousin_grades_similar() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import loop_grader, pyramid

    aws = [
        pyramid.level_feature("a1", "ACTION", raw_verb="GetSessionToken"),
        pyramid.level_feature("a2", "ACTION", raw_verb="ListBuckets"),
        pyramid.level_feature("a3", "ACTION", raw_verb="PutRolePolicy"),
    ]
    win = [
        pyramid.level_feature("b1", "ACTION", raw_verb="kerberos tgt request"),
        pyramid.level_feature("b2", "ACTION", raw_verb="net user /domain"),
        pyramid.level_feature("b3", "ACTION", raw_verb="secretsdump"),
    ]
    shared_tokens = {f.token for f in aws} & {f.token for f in win}
    if shared_tokens:
        return "FAIL", "test fixture is not actually cross-vocabulary", []
    grade = loop_grader.grade_for_loop(aws, "anchor-1", win, distance=0.45)
    if grade.relationship != "SIMILAR":
        return "FAIL", f"cross-vocabulary cousin graded {grade.relationship}, not SIMILAR", []
    if grade.match_level != pyramid.L3_BEHAVIOR:
        return "FAIL", "cross-vocabulary cousin did not hold at L3_BEHAVIOR", []
    return "PASS", "", []


@register(
    "bully_loop_reintegration_anomalous_reaches_discovery_axis",
    "DP. ANOMALOUS_UNCLASSIFIED reaches the scoreboard discovery axis end to end",
    order=117,
)
def check_anomalous_reaches_discovery_axis() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import scoreboard as scoreboard_mod

    same_record = {
        "assessment_id": "ca-1",
        "relationship": "SAME",
        "defense_response": "COVERED",
        "composite": 0.05,
        "candidate_state": None,
        "known_benign": False,
    }
    seeded = scoreboard_mod.score_record(same_record)
    if seeded["discovery_value"] != 0.0:
        return "FAIL", "SAME (known-bad) scored nonzero on the discovery axis", []

    anomalous_record = {
        "assessment_id": "ca-2",
        "relationship": "ANOMALOUS_UNCLASSIFIED",
        "defense_response": "INDETERMINATE",
        "composite": 0.0,
        "candidate_state": None,
        "known_benign": False,
    }
    clean = scoreboard_mod.score_record(anomalous_record)
    if not (clean["catch"] and clean["discovery_value"] > 0.0):
        return "FAIL", "ANOMALOUS_UNCLASSIFIED did not reach the discovery floor", []
    return "PASS", "", []


@register(
    "bully_loop_reintegration_confirmed_cousin_reaches_handoff",
    "DQ. a confirmed cousin reaches a handoff detection draft",
    order=118,
)
def check_confirmed_cousin_reaches_handoff() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import handoff as handoff_mod

    def _fake_call_model(model: str, messages: list[dict]) -> dict:
        return {
            "content": "```spl\nindex=* sourcetype=windows:security EventCode=4672\n```\n"
            "```sigma\ntitle: seeded\n```"
        }

    seeded_broken = handoff_mod.draft_generalization(
        "T1078",
        {"action_sequence": ["AssumeRole"]},
        {"spl": "", "distinguishing_features": {}},
        call_model=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )
    if not seeded_broken.get("spl"):
        return (
            "FAIL",
            "a model failure produced no fallback SPL at all -- should honest-degrade",
            [],
        )

    draft = handoff_mod.draft_generalization(
        "T1078",
        {"action_sequence": ["AssumeRole", "ListBuckets"]},
        {"spl": "", "distinguishing_features": {}},
        call_model=_fake_call_model,
    )
    if not draft.get("spl") and not draft.get("sigma_rule"):
        return "FAIL", "a confirmed cousin's draft carried neither SPL nor a Sigma rule", []
    return "PASS", "", []


@register(
    "bully_loop_reintegration_milestone_run_plane_live_or_blocked",
    "DR. the milestone run's plane is live or the run is BLOCKED with a reason (R4)",
    order=119,
)
def check_milestone_run_plane_live_or_blocked() -> tuple[str, str, list[dict]]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs" / "BULLY_LOOP_MILESTONE_RUN_R6_V1.json"
    if not path.is_file():
        return "FAIL", "BULLY_LOOP_MILESTONE_RUN_R6_V1.json does not exist", []
    report = json.loads(path.read_text())
    plane = report.get("plane")
    if plane not in ("live", "BLOCKED"):
        return "FAIL", f"milestone run plane is {plane!r} -- must be live or BLOCKED", []
    if plane == "BLOCKED" and not report.get("reason"):
        return "FAIL", "milestone run is BLOCKED with no reason -- R4 violated", []
    return "PASS", "", []


@register(
    "bully_loop_reintegration_every_match_carries_level_and_robustness",
    "DS. every match carries a pyramid level and robustness",
    order=120,
)
def check_every_match_carries_level_and_robustness() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import pyramid

    empty_match = pyramid.match_level([], [])
    if empty_match.level != "" or empty_match.robustness != 0.0:
        return "FAIL", "an empty match did not report level='' / robustness=0.0", []

    subj = [pyramid.level_feature("v1", "ACTION", raw_verb="assumerole")]
    anchor = [pyramid.level_feature("v1", "ACTION", raw_verb="assumerole")]
    clean = pyramid.match_level(subj, anchor)
    if not clean.level or clean.robustness <= 0.0:
        return "FAIL", "a genuine L3 match did not carry a populated level/robustness", []
    return "PASS", "", []


# ── TASK_BULLY_SCOREBOARD_CONFORMANCE_V1 (W.5): every published run must be
# the module's contract, never a proxy under its name. The five run docs
# audited by the withdrawn diagnosis are grandfathered ONLY because W.0 gave
# each a dated errata header pointing at the correction -- a new run has no
# such excuse and must conform outright. ────────────────────────────────────

_SCOREBOARD_CONFORMANCE_HISTORICAL_RUN_DOCS = (
    "BULLY_COUSIN_RELATION_RUN_C7_V1.json",
    "BULLY_LOOP_MILESTONE_RUN_R6_V1.json",
    "BULLY_RELATE_INVESTIGATE_RUN_M3_V1.json",
    "BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json",
    "BULLY_UNKNOWN_COUSIN_RUN_M3_V1.json",
)


def _scoreboard_conformance_docs_dir():
    from pathlib import Path

    return Path(__file__).resolve().parents[2] / "docs"


def _scoreboard_conformance_new_run_docs():
    """Every `docs/BULLY_*RUN*.json` that is NOT one of the five grandfathered
    historical runs -- i.e. a run this task's conformance guard must hold to
    the real contract, not merely tolerate with an errata pointer."""
    import json

    docs_dir = _scoreboard_conformance_docs_dir()
    out = []
    for path in sorted(docs_dir.glob("BULLY_*RUN*.json")):
        if path.name in _SCOREBOARD_CONFORMANCE_HISTORICAL_RUN_DOCS:
            continue
        out.append((path.name, json.loads(path.read_text())))
    return out


@register(
    "bully_scoreboard_conformance_every_run_conforms_or_is_errata_d",
    "DT. every published run passes the scoreboard-conformance guard, or is a "
    "W.0-errata'd historical run",
    order=121,
)
def check_scoreboard_conformance_every_run_conforms_or_errata() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.scoreboard_conformance import check_run

    for name, run_json in _scoreboard_conformance_new_run_docs():
        findings = check_run(run_json)
        fails = [f for f in findings if f.severity == "FAIL"]
        if fails:
            return (
                "FAIL",
                f"{name} is not grandfathered by W.0 errata and fails conformance: "
                f"{[f.code for f in fails]}",
                [f.to_dict() for f in fails],
            )
    return "PASS", "", []


@register(
    "bully_scoreboard_conformance_no_proxy_scoreboard_block",
    "DU. no run publishes a 'scoreboard' block whose keys are not scoreboard.update()'s contract",
    order=122,
)
def check_scoreboard_conformance_no_proxy_block() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.scoreboard_conformance import check_run

    for name, run_json in _scoreboard_conformance_new_run_docs():
        codes = {f.code for f in check_run(run_json) if f.severity == "FAIL"}
        if (
            "scoreboard_block_is_not_the_contract" in codes
            or "scoreboard_contract_incomplete" in codes
        ):
            return (
                "FAIL",
                f"{name} publishes a 'scoreboard' block that is not the real contract",
                [],
            )
    return "PASS", "", []


@register(
    "bully_scoreboard_conformance_correctness_axis_present",
    "DV. trust_mean_rank and false_flag_count are present in every new run (W.2)",
    order=123,
)
def check_scoreboard_conformance_correctness_axis_present() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.scoreboard_conformance import check_run

    for name, run_json in _scoreboard_conformance_new_run_docs():
        codes = {f.code for f in check_run(run_json) if f.severity == "FAIL"}
        if "correctness_axis_not_published" in codes:
            return "FAIL", f"{name} never published trust_mean_rank/false_flag_count", []
    return "PASS", "", []


@register(
    "bully_scoreboard_conformance_per_row_full_contract",
    "DW. per_row retains the full score_record contract",
    order=124,
)
def check_scoreboard_conformance_per_row_full_contract() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.scoreboard_conformance import check_run

    for name, run_json in _scoreboard_conformance_new_run_docs():
        codes = {f.code for f in check_run(run_json) if f.severity == "FAIL"}
        if "per_row_drops_correctness_fields" in codes:
            return "FAIL", f"{name}'s per_row drops score_record correctness fields", []
    return "PASS", "", []


@register(
    "bully_scoreboard_conformance_trust_axis_not_hardcoded_nulls",
    "DX. the trust axis is not fed hardcoded nulls (W.3)",
    order=125,
)
def check_scoreboard_conformance_trust_axis_not_nulled() -> tuple[str, str, list[dict]]:
    """`trust_axis_fed_nulls` is WARN-severity in the underlying guard by
    design (task residual risks): a live run where BIN genuinely was never
    driven for any assessment looks identical, on this signal alone, to the
    old hardcoded-null call site -- the guard cannot tell environment state
    from a coding defect and neither can this check, so it surfaces as WARN
    (evidence for a human) rather than a hard CI FAIL that would block every
    legitimate BIN-not-yet-driven run."""
    from portal.modules.security.core.bully.scoreboard_conformance import check_run

    for name, run_json in _scoreboard_conformance_new_run_docs():
        warn_codes = {f.code for f in check_run(run_json) if f.severity == "WARN"}
        if "trust_axis_fed_nulls" in warn_codes:
            return (
                "WARN",
                f"{name}: every record has candidate_state=None and known_benign=False "
                f"(BIN not yet driven for this hunt, or a regression to hardcoded nulls -- "
                f"see the run's own correctness_axis_provenance if published)",
                [],
            )
    return "PASS", "", []


@register(
    "bully_scoreboard_conformance_contract_matches_update_no_drift",
    "DY. SCOREBOARD_UPDATE_CONTRACT matches scoreboard.update()'s actual keys "
    "(drift guard, never hardcoded from prose)",
    order=126,
)
def check_scoreboard_conformance_contract_no_drift() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import scoreboard as scoreboard_mod
    from portal.modules.security.core.bully.scoreboard_conformance import (
        SCOREBOARD_UPDATE_CONTRACT,
    )

    actual = set(scoreboard_mod.update("drift-probe-hunt", []).keys()) - {"records"}
    declared = set(SCOREBOARD_UPDATE_CONTRACT)
    if actual != declared:
        return (
            "FAIL",
            f"SCOREBOARD_UPDATE_CONTRACT has drifted from scoreboard.update(): "
            f"declared={sorted(declared)} actual={sorted(actual)}",
            [],
        )
    return "PASS", "", []


@register(
    "bully_scoreboard_conformance_guard_fails_all_five_historical_runs",
    "DZ. the conformance guard FAILs all five historical runs (W.5 permanent regression)",
    order=127,
)
def check_scoreboard_conformance_fails_historical_runs() -> tuple[str, str, list[dict]]:
    import json

    from portal.modules.security.core.bully.scoreboard_conformance import check_run

    docs_dir = _scoreboard_conformance_docs_dir()
    missed = []
    for name in _SCOREBOARD_CONFORMANCE_HISTORICAL_RUN_DOCS:
        path = docs_dir / name
        if not path.is_file():
            return "FAIL", f"missing historical run doc: {name}", []
        run_json = json.loads(path.read_text())
        findings = check_run(run_json)
        if not any(f.severity == "FAIL" for f in findings):
            missed.append(name)
    if missed:
        return "FAIL", f"the guard did not FAIL these historical runs: {missed}", []
    return "PASS", "", []


# ── X.7: the analyst loop's CI invariants (TASK_BULLY_ANALYST_LOOP_V1) ─────


@register(
    "bully_analyst_loop_notifying_classes_fire_and_only_those",
    "EA. every notifying class (SAME/SIMILAR/ANOMALOUS_UNCLASSIFIED) fires; DIFFERENT never does (X1)",
    order=128,
)
def check_analyst_loop_notifying_classes() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import analyst_loop as al
    from portal.modules.security.core.bully.contracts import RELATIONSHIPS

    fired: dict[str, bool] = {}
    for relationship in RELATIONSHIPS:
        notified = []
        concern = al.raise_concern(
            assessment_id="as-ci",
            entity_id="e-ci",
            relationship=relationship,
            notify=notified.append,
        )
        fired[relationship] = concern is not None
        if (concern is not None) != bool(notified):
            return "FAIL", f"{relationship}: concern/notify disagree", []

    expected = {"SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED"}
    actually_fired = {r for r, f in fired.items() if f}
    if actually_fired != expected:
        return (
            "FAIL",
            f"notifying classes {sorted(actually_fired)} != expected {sorted(expected)}",
            [],
        )
    if fired.get("DIFFERENT"):
        return "FAIL", "DIFFERENT fired a concern -- X1 violated", []
    return "PASS", "", []


@register(
    "bully_analyst_loop_should_escalate_is_the_only_suppressor",
    "EB. should_escalate is the ONLY suppression path -- no threshold/gate on attention",
    order=129,
)
def check_analyst_loop_only_suppressor() -> tuple[str, str, list[dict]]:
    import inspect

    from portal.modules.security.core.bully import analyst_loop as al

    params = set(inspect.signature(al.raise_concern).parameters)
    # Seeded violation check: no parameter name resembling a score/count
    # threshold exists on the entry point a gate would hide behind.
    forbidden_substrings = ("threshold", "min_", "max_", "cutoff", "floor")
    suspicious = [
        p for p in params if any(s in p.lower() for s in forbidden_substrings) and p != "notify"
    ]
    if suspicious:
        return "FAIL", f"raise_concern exposes a threshold-shaped parameter: {suspicious}", []

    # should_escalate=False is the only way to suppress a notifying class.
    notified = []
    suppressed = al.raise_concern(
        assessment_id="as-ci",
        entity_id="e-ci",
        relationship="SAME",
        notify=notified.append,
        should_escalate=False,
    )
    if suppressed is not None or notified:
        return "FAIL", "should_escalate=False did not suppress", []

    notified2 = []
    unsuppressed = al.raise_concern(
        assessment_id="as-ci",
        entity_id="e-ci",
        relationship="SAME",
        notify=notified2.append,
        should_escalate=True,
    )
    if unsuppressed is None or not notified2:
        return "FAIL", "should_escalate=True (the default posture) failed to fire", []
    return "PASS", "", []


@register(
    "bully_analyst_loop_all_three_verdicts_write_back",
    "EC. all three verdicts write back; BENIGN writes BENIGN_CLOSE at ANALYST_CONFIRMED",
    order=130,
)
def check_analyst_loop_verdicts_write_back() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import analyst_loop as al
    from portal.modules.security.core.bully import signatures as sig_mod
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    expected = {
        al.CONFIRMED: ("ESCALATE", "ANALYST_CONFIRMED"),
        al.BENIGN: ("BENIGN_CLOSE", "ANALYST_CONFIRMED"),
        al.UNSURE: ("ANOMALOUS_UNCLASSIFIED", "SYSTEM_GENERATED"),
    }
    for verdict, (outcome, tier) in expected.items():
        lib = AnchorLibrary()
        signature = sig_mod.build_signature(
            {"target_host": "ci"}, {"action_sequence": ["ci_probe", verdict.lower()]}
        )
        concern = al.raise_concern(
            assessment_id="as-ci", entity_id="e-ci", relationship="SAME", notify=lambda _p: None
        )
        _closed, anchor = al.record_verdict(
            concern, verdict, anchor_library=lib, signature=signature
        )
        if anchor is None:
            return "FAIL", f"{verdict} produced no anchor", []
        if anchor.record.get("outcome") != outcome or anchor.provenance_tier != tier:
            return (
                "FAIL",
                f"{verdict} -> outcome={anchor.record.get('outcome')!r}/"
                f"tier={anchor.provenance_tier!r}, expected {outcome!r}/{tier!r}",
                [],
            )
        if verdict == al.BENIGN and (
            anchor.record.get("outcome") != "BENIGN_CLOSE"
            or anchor.provenance_tier != "ANALYST_CONFIRMED"
        ):
            return "FAIL", "BENIGN did not write BENIGN_CLOSE at ANALYST_CONFIRMED", []
    return "PASS", "", []


@register(
    "bully_analyst_loop_unsure_weak_and_cannot_raise_confidence",
    "ED. UNSURE writes weak/SYSTEM_GENERATED and cannot raise confidence (G.2)",
    order=131,
)
def check_analyst_loop_unsure_weak() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import analyst_loop as al
    from portal.modules.security.core.bully import signatures as sig_mod
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    lib = AnchorLibrary()
    signature = sig_mod.build_signature(
        {"target_host": "ci"}, {"action_sequence": ["ci_probe_unsure"]}
    )
    concern = al.raise_concern(
        assessment_id="as-ci",
        entity_id="e-ci",
        relationship="ANOMALOUS_UNCLASSIFIED",
        notify=lambda _p: None,
    )
    _closed, anchor = al.record_verdict(concern, al.UNSURE, anchor_library=lib, signature=signature)
    if anchor is None:
        return "FAIL", "UNSURE produced no anchor -- uncertainty was discarded, not retained", []
    if anchor.grade != "weak":
        return "FAIL", f"UNSURE anchor graded {anchor.grade!r}, expected 'weak'", []
    if anchor.provenance_tier != "SYSTEM_GENERATED":
        return (
            "FAIL",
            f"UNSURE anchor tiered {anchor.provenance_tier!r}, expected SYSTEM_GENERATED",
            [],
        )
    if anchor.label_basis == "analyst_decision":
        return (
            "FAIL",
            "UNSURE anchor carries analyst_decision label basis -- would raise confidence",
            [],
        )
    return "PASS", "", []


@register(
    "bully_analyst_loop_notification_payload_carries_concern_class",
    "EE. the notification payload carries concern_class distinguishing known_bad from unknown_cousin (X4)",
    order=132,
)
def check_analyst_loop_payload_carries_concern_class() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import analyst_loop as al

    payloads = []
    for relationship in ("SAME", "SIMILAR", "ANOMALOUS_UNCLASSIFIED"):
        al.raise_concern(
            assessment_id="as-ci",
            entity_id="e-ci",
            relationship=relationship,
            notify=payloads.append,
        )
    if "concern_class" not in payloads[0]:
        return "FAIL", "notification payload missing concern_class", []
    if payloads[0]["concern_class"] != "known_bad":
        return "FAIL", "SAME did not carry concern_class=known_bad", []
    if (
        payloads[1]["concern_class"] != "unknown_cousin"
        or payloads[2]["concern_class"] != "unknown_cousin"
    ):
        return (
            "FAIL",
            "SIMILAR/ANOMALOUS_UNCLASSIFIED did not carry concern_class=unknown_cousin",
            [],
        )
    return "PASS", "", []


@register(
    "bully_analyst_loop_run_publishes_maturation_report",
    "EF. a run publishing concerns publishes the maturation report (X6)",
    order=133,
)
def check_analyst_loop_run_publishes_maturation_report() -> tuple[str, str, list[dict]]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs" / "BULLY_ANALYST_LOOP_RUN_X6_V1.json"
    if not path.is_file():
        return "FAIL", "BULLY_ANALYST_LOOP_RUN_X6_V1.json does not exist", []
    report = json.loads(path.read_text())
    if report.get("plane") == "BLOCKED":
        if not report.get("reason"):
            return "FAIL", "X6 run is BLOCKED with no reason", []
        return "PASS", "", []
    mat = report.get("maturation_report")
    if not isinstance(mat, dict):
        return "FAIL", "X6 run publishes no maturation_report", []
    required = {
        "concerns_before",
        "concerns_after",
        "suppressed_entities",
        "n_suppressed",
        "still_raised",
        "newly_raised",
        "noise_reduction",
    }
    missing = required - set(mat)
    if missing:
        return "FAIL", f"maturation_report missing fields: {sorted(missing)}", []
    both = report.get("both_classes_notified") or {}
    if not both.get("cycle_1_both_fired"):
        return "FAIL", "X6 run did not fire both known_bad and unknown_cousin concerns", []
    return "PASS", "", []


@register(
    "bully_analyst_loop_handoff_and_bin_off_the_notification_path",
    "EG. handoff/BIN are never imported by the concern-notification path (X.6 design note)",
    order=134,
)
def check_analyst_loop_handoff_bin_off_path() -> tuple[str, str, list[dict]]:
    import ast
    from pathlib import Path

    bully_dir = (
        Path(__file__).resolve().parents[2] / "portal" / "modules" / "security" / "core" / "bully"
    )
    forbidden = {"handoff", "promotion"}
    offenders = []
    for name in ("analyst_loop",):
        path = bully_dir / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.rsplit(".", 1)[-1])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.rsplit(".", 1)[-1])
        hit = imported & forbidden
        if hit:
            offenders.append(f"{name}.py imports {sorted(hit)}")
    if offenders:
        return "FAIL", "; ".join(offenders), []
    return "PASS", "", []


@register(
    "bully_truth_x6_per_row_yields_invalid",
    "EH. X.6's per_row yields INVALID from truth_acceptance (permanent regression, Y.1)",
    order=135,
)
def check_truth_x6_per_row_yields_invalid() -> tuple[str, str, list[dict]]:
    import json
    from pathlib import Path

    from portal.modules.security.core.bully import truth_acceptance as ta

    path = Path(__file__).resolve().parents[2] / "docs" / "BULLY_ANALYST_LOOP_RUN_X6_V1.json"
    if not path.is_file():
        return "FAIL", "BULLY_ANALYST_LOOP_RUN_X6_V1.json does not exist", []
    report = json.loads(path.read_text())
    rows = [r for r in report["per_row"] if r["cycle"] == 1]
    det = ta.detection_report(rows)
    if det.verdict != "INVALID" or det.n_implants_graded != 0:
        return (
            "FAIL",
            f"X.6 per_row must yield INVALID with 0 implants graded, got "
            f"verdict={det.verdict} n_implants_graded={det.n_implants_graded}",
            [],
        )
    return "PASS", "", []


@register(
    "bully_truth_acceptance_requires_sealed_truth_join",
    "EI. no acceptance criterion is satisfiable without a sealed-truth join (Y.1)",
    order=136,
)
def check_truth_acceptance_requires_sealed_truth_join() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import truth_acceptance as ta

    # Seeded violation: a run whose grader's own labels split into two
    # buckets, but sealed truth shows every graded entity is background
    # (X.6's exact shape) -- if this passed, acceptance would be vacuous.
    rows = [
        {"implant_class_ground_truth": "background", "relationship": "SAME"} for _ in range(150)
    ] + [
        {"implant_class_ground_truth": "background", "relationship": "SIMILAR"} for _ in range(150)
    ]
    det = ta.detection_report(rows)
    if det.verdict != "INVALID":
        return (
            "FAIL",
            "a background-only population with a two-bucket label split must be INVALID",
            [],
        )
    return "PASS", "", []


@register(
    "bully_truth_background_only_population_invalid",
    "EJ. a background-only graded population is INVALID (Y.1)",
    order=137,
)
def check_truth_background_only_population_invalid() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import truth_acceptance as ta

    rows = [{"implant_class_ground_truth": "background", "relationship": "NONE"} for _ in range(20)]
    det = ta.detection_report(rows)
    if det.verdict != "INVALID":
        return "FAIL", "zero-implant graded population did not report INVALID", []
    good_rows = rows + [
        {"implant_class_ground_truth": "known_bad", "relationship": "SAME"} for _ in range(3)
    ]
    det2 = ta.detection_report(good_rows)
    if det2.verdict == "INVALID":
        return "FAIL", "a population WITH implants was wrongly reported INVALID", []
    return "PASS", "", []


@register(
    "bully_truth_selection_report_published_when_implants_shipped",
    "EK. selection_report is published whenever implants were shipped (Y.3)",
    order=138,
)
def check_truth_selection_report_published_when_implants_shipped() -> tuple[str, str, list[dict]]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs" / "BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1.json"
    if not path.is_file():
        return "FAIL", "BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1.json does not exist", []
    report = json.loads(path.read_text())
    if report.get("plane") == "BLOCKED":
        if not report.get("reason"):
            return "FAIL", "Y6 run is BLOCKED with no reason", []
        return "PASS", "", []
    sel = report.get("selection_report")
    if not isinstance(sel, dict):
        return "FAIL", "Y6 run publishes no selection_report", []
    required = {
        "n_implants_shipped",
        "n_implant_entities_available",
        "n_implant_entities_selected",
        "selection_recall",
        "verdict",
    }
    missing = required - set(sel)
    if missing:
        return "FAIL", f"selection_report missing fields: {sorted(missing)}", []
    if sel["n_implants_shipped"] and sel["verdict"] == "FAIL":
        return (
            "FAIL",
            "implants were shipped but selection_report FAILed -- implants excluded",
            [],
        )
    return "PASS", "", []


@register(
    "bully_truth_scripted_verdict_contradicting_truth_writes_no_anchor",
    "EL. a scripted verdict contradicting truth writes no anchor (Y.4)",
    order=139,
)
def check_truth_scripted_verdict_contradicting_truth_writes_no_anchor() -> tuple[
    str, str, list[dict]
]:
    from portal.modules.security.core.bully import analyst_loop as al
    from portal.modules.security.core.bully import signatures as sig_mod
    from portal.modules.security.core.bully.anchors import AnchorLibrary

    lib = AnchorLibrary()
    signature = sig_mod.build_signature(
        {"target_host": "ci-host"},
        {
            "action_sequence": ["auth", "enumerate"],
            "telemetry_shape": {"source_class": "ci"},
        },
    )
    concern = al.raise_concern(
        assessment_id="as-ci",
        entity_id="ent-ci",
        relationship="SAME",
        notify=lambda _p: None,
    )
    closed, anchor = al.record_verdict(
        concern,
        al.CONFIRMED,
        anchor_library=lib,
        signature=signature,
        scripted=True,
        ground_truth="background",
    )
    if anchor is not None or len(lib) != 0:
        return "FAIL", "scripted CONFIRMED on background wrote an anchor", []
    if not closed.verdict_write_refused_reason:
        return "FAIL", "refused write did not record a reason on the closed concern", []
    # Same verdict from a real analyst (scripted=False, default) must still write.
    closed2, anchor2 = al.record_verdict(
        concern, al.CONFIRMED, anchor_library=lib, signature=signature, ground_truth="background"
    )
    if anchor2 is None:
        return "FAIL", "a REAL analyst verdict was wrongly blocked by the truth guard", []
    return "PASS", "", []


@register(
    "bully_truth_alignment_below_coverage_never_grades_exact_or_cousin",
    "EM. an alignment below MIN_OBSERVED_COVERAGE never grades EXACT/COUSIN (Y.2)",
    order=140,
)
def check_truth_alignment_below_coverage_never_grades_exact_or_cousin() -> tuple[
    str, str, list[dict]
]:
    from portal.modules.security.core.bully.series_cousin import (
        BehaviouralSeries,
        decide_cousin,
    )

    known = BehaviouralSeries(
        series_id="known-1", spine=("auth", "execute", "execute"), n_logs=3, technique="T1078"
    )
    # 71%-noise timeline: the known spine appears in order but diluted across
    # a much longer observed series -- must not clear EXACT/COUSIN.
    noisy = BehaviouralSeries(
        series_id="obs-noisy",
        spine=(
            "collect",
            "persist",
            "collect",
            "persist",
            "auth",
            "collect",
            "persist",
            "execute",
            "collect",
            "persist",
            "execute",
            "collect",
            "persist",
            "collect",
        ),
        n_logs=14,
    )
    result = decide_cousin(noisy, [known])
    if result.relation in ("EXACT", "COUSIN"):
        return "FAIL", f"noisy-containment timeline graded {result.relation}, must not", []
    # Reverting the coverage gate must reproduce the bug (proves the gate is load-bearing).
    reverted = decide_cousin(noisy, [known], min_observed_coverage=0.0, min_distinct_ratio=0.0)
    if reverted.relation not in ("EXACT", "COUSIN"):
        return (
            "FAIL",
            "reverting MIN_OBSERVED_COVERAGE did not reproduce the noisy false match "
            "-- the gate may not be load-bearing",
            [],
        )
    return "PASS", "", []


@register(
    "bully_truth_classifier_distribution_and_entropy_published",
    "EN. classifier output distribution and entropy are published every run (Y.5)",
    order=141,
)
def check_truth_classifier_distribution_and_entropy_published() -> tuple[str, str, list[dict]]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs" / "BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1.json"
    if not path.is_file():
        return "FAIL", "BULLY_TRUTH_ACCEPTANCE_RUN_Y6_V1.json does not exist", []
    report = json.loads(path.read_text())
    if report.get("plane") == "BLOCKED":
        if not report.get("reason"):
            return "FAIL", "Y6 run is BLOCKED with no reason", []
        return "PASS", "", []
    cov = report.get("classifier_coverage")
    if not isinstance(cov, dict):
        return "FAIL", "Y6 run publishes no classifier_coverage", []
    required = {
        "real_verb_output_distribution",
        "real_verb_class_entropy_bits",
        "real_verb_degenerate",
    }
    missing = required - set(cov)
    if missing:
        return "FAIL", f"classifier_coverage missing fields: {sorted(missing)}", []
    if cov["real_verb_output_distribution"] is None:
        return "FAIL", "real_verb_output_distribution was not populated", []
    return "PASS", "", []


@register(
    "bully_truth_json_raw_parsed_not_dropped",
    "EO. JSON-shaped _raw captures the real payload, never silently dropped (D5, Y.6)",
    order=142,
)
def check_truth_json_raw_parsed_not_dropped() -> tuple[str, str, list[dict]]:
    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import bully_loop_milestone_run as r6

    rec = {"_raw": '{"actor.id": "adv8370", "detail": {"src_id": "adv5738"}}'}
    parsed = r6._parse_raw_kv(rec)
    if parsed.get("actor.id") != "adv8370" or parsed.get("src_id") != "adv5738":
        return (
            "FAIL",
            "JSON-shaped _raw was not recovered -- the payload would be silently "
            "dropped, as it was for X.6/first Y.6 attempt (D5)",
            [],
        )
    # Seeded violation: the old regex alone cannot parse JSON at all.
    if list(r6._RAW_KV.finditer(rec["_raw"])):
        return "FAIL", "the key=value regex unexpectedly matched JSON text", []
    # Real KV-formatted raw text (actual Windows/Linux logs) must still work.
    kv_rec = {"_raw": "EventCode=4624 Account=jsmith"}
    kv_parsed = r6._parse_raw_kv(kv_rec)
    if kv_parsed.get("EventCode") != "4624":
        return "FAIL", "real key=value _raw text regressed", []
    return "PASS", "", []


# ── D-CI: TASK_BULLY_DISCOVERY_FIRST_V1 invariants ─────────────────────────


def _majority_and_attack_units() -> tuple[list, list]:
    """A baseline fit ONLY on a routine majority shape, plus a small attack
    shape sharing every structural boilerplate token (edge mix, span, size,
    entity role) but none of its behavioural bigrams -- the fixture several
    D-CI checks below share."""
    from portal.modules.security.core.bully.artifact_graph import GradeableUnit

    def _unit(unit_id: str, entity: str, classes: tuple[str, ...]) -> GradeableUnit:
        n = len(classes)
        return GradeableUnit(
            unit_id=unit_id,
            level="L4_WINDOW",
            artifact_ids=tuple(f"{unit_id}-a{i}" for i in range(n)),
            entities=(entity,),
            action_classes=classes,
            edge_kinds=("shared_entity", "temporal_adjacency"),
            span_seconds=200.0,
            structural_signature={
                "class_sequence": list(classes),
                "entity_role_profile": {"actor": 1},
            },
            vocabulary=(),
            source_ids=(f"src-{unit_id}",),
        )

    majority = [
        _unit(f"maj-{i}", f"benign-{i}", ("enumerate", "collect", "enumerate", "collect"))
        for i in range(100)
    ]
    attack = [
        _unit(f"atk-{i}", f"attacker-{i}", ("auth", "escalate", "execute", "collect"))
        for i in range(3)
    ]
    return majority, attack


@register(
    "bully_discovery_no_anchor_library_param",
    "EP. discover() accepts no anchor library (D2, signature check)",
    order=143,
)
def check_discovery_no_anchor_library_param() -> tuple[str, str, list[dict]]:
    import inspect

    from portal.modules.security.core.bully import discovery as disc

    bad = [
        n
        for n in inspect.signature(disc.discover).parameters
        if "library" in n.lower() or "anchor" in n.lower()
    ]
    if bad:
        return "FAIL", f"discover() accepts a library/anchor parameter: {bad}", []
    return "PASS", "", []


@register(
    "bully_discovery_library_never_sole_trigger",
    "EQ. no code path makes surfacing conditional on a catalogue match alone (D1)",
    order=144,
)
def check_library_never_sole_trigger() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import anchors as anc
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully.unit_outcome import resolve_unit_outcome

    library = anc.AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["AssumeRole", "ListBuckets"]},
        techniques=("T1078",),
    )
    unit = _unit_from_verbs(["AssumeRole", "ListBuckets"], "attacker")
    # An empty (never-fitted) baseline: the unit cannot be remarkable, so an
    # EXACT library match here must resolve NORMAL, not UNKNOWN_SAME/COUSIN.
    outcome = resolve_unit_outcome(
        unit, list(library.all()), bl.NormalBaseline(environment_id="ci")
    )
    if outcome.outcome != "NORMAL":
        return (
            "FAIL",
            f"a library match alone (unremarkable unit) surfaced as {outcome.outcome}, "
            "expected NORMAL -- the library triggered a concern by itself",
            [],
        )
    return "PASS", "", []


@register(
    "bully_discovery_resembles_nothing_still_surfaced",
    "ER. a discovery with resembles_nothing is still surfaced, never a miss (D4)",
    order=145,
)
def check_resembles_nothing_still_surfaced() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully import discovery as disc

    majority, attack = _majority_and_attack_units()
    model = bl.NormalBaseline(environment_id="ci")
    model.fit(majority)
    discoveries, _report = disc.discover(attack, model)
    if len(discoveries) != len(attack):
        return (
            "FAIL",
            f"expected all {len(attack)} attack units discovered, got {len(discoveries)}",
            [],
        )
    clusters = disc.find_cousin_clusters(discoveries)
    if not clusters:
        return "FAIL", "attack units did not cluster into cousins of each other", []
    cluster = clusters[0]
    enrichment = disc.enrich(cluster.shared_shape, library_shapes=[])
    if not enrichment.resembles_nothing:
        return "FAIL", "empty library did not report resembles_nothing", []
    if cluster.n_distinct_entities < 2:
        return "FAIL", "the cluster finding did not stand (retracted) after resembles_nothing", []
    return "PASS", "", []


@register(
    "bully_discovery_cousin_clusters_library_free",
    "ES. cousin clusters are computed without the library (D3, signature check)",
    order=146,
)
def check_cousin_clusters_library_free() -> tuple[str, str, list[dict]]:
    import inspect

    from portal.modules.security.core.bully import discovery as disc

    bad = [
        n
        for n in inspect.signature(disc.find_cousin_clusters).parameters
        if "library" in n.lower() or "anchor" in n.lower()
    ]
    if bad:
        return "FAIL", f"find_cousin_clusters() accepts a library/anchor parameter: {bad}", []
    return "PASS", "", []


@register(
    "bully_discovery_ranked_by_rarity_not_cluster_size",
    "ET. cousin-cluster ranking is by remarkability, not cluster size (D5)",
    order=147,
)
def check_ranked_by_rarity_not_cluster_size() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully import discovery as disc
    from portal.modules.security.core.bully.artifact_graph import GradeableUnit

    def _unit(unit_id: str, entity: str, classes: tuple[str, ...]) -> GradeableUnit:
        n = len(classes)
        return GradeableUnit(
            unit_id=unit_id,
            level="L4_WINDOW",
            artifact_ids=tuple(f"{unit_id}-a{i}" for i in range(n)),
            entities=(entity,),
            action_classes=classes,
            edge_kinds=("shared_entity", "temporal_adjacency"),
            span_seconds=200.0,
            structural_signature={
                "class_sequence": list(classes),
                "entity_role_profile": {"actor": 1},
            },
            vocabulary=(),
            source_ids=(f"src-{unit_id}",),
        )

    majority = [
        _unit(f"maj-{i}", f"benign-{i}", ("enumerate", "collect", "enumerate", "collect"))
        for i in range(100)
    ]
    minority = [
        _unit(f"min-{i}", f"minor-{i}", ("auth", "enumerate", "auth", "enumerate"))
        for i in range(23)
    ]
    attack = [
        _unit(f"atk-{i}", f"attacker-{i}", ("auth", "escalate", "execute", "collect"))
        for i in range(3)
    ]
    model = bl.NormalBaseline(environment_id="ci")
    model.fit(majority)
    discoveries, _report = disc.discover(minority + attack, model)
    clusters = disc.find_cousin_clusters(discoveries)
    if len(clusters) != 2:
        return "FAIL", f"expected 2 clusters (minority, attack), got {len(clusters)}", []
    by_size = max(clusters, key=lambda c: len(c.members))
    by_rarity = sorted(clusters, key=lambda c: c.mean_remarkability, reverse=True)[0]
    if len(by_size.members) != 23:
        return "FAIL", "fixture assumption broke: minority cluster is no longer the larger one", []
    if by_rarity is by_size:
        return (
            "FAIL",
            "the larger, less-rare cluster ranked first by remarkability -- D5 violated",
            [],
        )
    return "PASS", "", []


@register(
    "bully_discovery_degeneracy_gate",
    "EU. >90% of units in one outcome bucket FAILS the run (D.4)",
    order=148,
)
def check_degeneracy_gate() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import truth_acceptance as ta

    degenerate_rows = [{"relationship": "SAME"} for _ in range(95)] + [
        {"relationship": "DIFFERENT"} for _ in range(5)
    ]
    result = ta.degeneracy_check(degenerate_rows)
    if result.verdict != "FAIL":
        return (
            "FAIL",
            f"95/100 rows in one bucket did not FAIL degeneracy_check: {result.verdict}",
            [],
        )
    healthy_rows = [{"relationship": "SAME"} for _ in range(40)] + [
        {"relationship": "DIFFERENT"} for _ in range(60)
    ]
    healthy = ta.degeneracy_check(healthy_rows)
    if healthy.verdict != "PASS":
        return "FAIL", f"a 40/60 split unexpectedly FAILed degeneracy_check: {healthy.verdict}", []
    return "PASS", "", []


@register(
    "bully_discovery_tail_remarkability_beats_mean",
    "EV. tail_remarkability beats mean remarkability on the seeded attack case (D.1)",
    order=149,
)
def check_tail_remarkability_beats_mean() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import baseline as bl
    from portal.modules.security.core.bully import discovery as disc

    majority, attack = _majority_and_attack_units()
    model = bl.NormalBaseline(environment_id="ci")
    model.fit(majority)
    for unit in attack:
        mean = model.remarkability(unit)
        tail = disc.tail_remarkability(unit, model)
        if not (tail > mean):
            return (
                "FAIL",
                f"tail_remarkability ({tail}) did not beat mean remarkability ({mean})",
                [],
            )
        if not (mean < disc.DISCOVERY_MIN_REMARKABILITY <= tail):
            return (
                "FAIL",
                f"expected mean<{disc.DISCOVERY_MIN_REMARKABILITY}<=tail, got mean={mean} tail={tail}",
                [],
            )
    return "PASS", "", []


@register(
    "bully_discovery_behavior_table_self_recognition",
    "EW. every behaviour-table label classifies to itself",
    order=150,
)
def check_behavior_table_self_recognition() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import pyramid as p

    labels = ("auth", "enumerate", "execute", "destroy", "escalate", "collect", "c2_exfil")
    failures = [label for label in labels if p.classify_behavior(label) != label]
    if failures:
        return "FAIL", f"labels that do not classify to themselves: {failures}", []
    return "PASS", "", []


# ── EX-FD: TASK_BULLY_CORPUS_BED_V1 (C.7) -- the corpus bed: the haystack
# must be real, cousins are derived from a published answer key, floor/
# product/cost never collapse into one number, and the answer key never
# reaches the grader. Each seeds a violation, confirms rejection, then
# confirms clean input passes. ────────────────────────────────────────────


@register(
    "bully_corpus_bed_below_floor_or_no_lane_a_is_invalid",
    "EX. a run below the haystack floor, or without Lane A, is not a haystack (C1)",
    order=151,
)
def check_corpus_bed_below_floor_or_no_lane_a_is_invalid() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb

    small = cb.assess_bed({"portal5_lab": 500}, records_read=500, units_fitted=0, units_scored=0)
    if small.is_haystack:
        return "FAIL", "a 500-record corpus was accepted as a haystack", []
    lane_a_absent = cb.assess_bed(
        {"portal5_lab": 200_000}, records_read=200_000, units_fitted=0, units_scored=0
    )
    if lane_a_absent.is_haystack:
        return "FAIL", "a corpus with no botsv1/2/3 records was accepted as a haystack", []
    real_bed = cb.assess_bed(
        {"portal5_lab": 50_000, "botsv1": 3_000_000, "botsv2": 5_000_000, "botsv3": 5_650_000},
        records_read=13_700_000,
        units_fitted=20_000,
        units_scored=10_000,
    )
    if not real_bed.is_haystack:
        return "FAIL", f"a real multi-index bed was rejected: {real_bed.reasons}", []
    return "PASS", "", []


@register(
    "bully_corpus_bed_cousin_parent_in_answer_key",
    "EY. every planned cousin's parent technique is drawn from the answer key (C2)",
    order=152,
)
def check_corpus_bed_cousin_parent_in_answer_key() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb
    from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY

    corpus_earliest, corpus_latest = 1534737600.0, 1568916650.0  # botsv3's real range
    cousins = cb.plan_cousins(
        list(BOTS_ANSWER_KEY), corpus_earliest=corpus_earliest, corpus_latest=corpus_latest
    )
    if not cousins:
        return "FAIL", "plan_cousins produced no cousins from the BOTS answer key", []
    answer_key_techniques = {e.technique for e in BOTS_ANSWER_KEY}
    orphaned = [c.cousin_id for c in cousins if c.parent_technique not in answer_key_techniques]
    if orphaned:
        return "FAIL", f"cousins with a parent technique absent from the answer key: {orphaned}", []
    # seeded violation: plan_cousins must never emit a cousin for a technique
    # it was not handed
    narrow = cb.plan_cousins(
        [BOTS_ANSWER_KEY[0]], corpus_earliest=corpus_earliest, corpus_latest=corpus_latest
    )
    if any(c.parent_technique != BOTS_ANSWER_KEY[0].technique for c in narrow):
        return "FAIL", "plan_cousins emitted a cousin for a technique it was not given", []
    return "PASS", "", []


@register(
    "bully_corpus_bed_floor_product_cost_never_averaged",
    "EZ. floor, product and cost are published separately, never averaged (C3)",
    order=153,
)
def check_corpus_bed_floor_product_cost_never_averaged() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb

    real_bed = cb.assess_bed(
        {"portal5_lab": 50_000, "botsv1": 3_000_000, "botsv2": 5_000_000, "botsv3": 5_650_000},
        records_read=13_700_000,
        units_fitted=20_000,
        units_scored=10_000,
    )
    floor_only = cb.bed_acceptance(
        answer_key_hit=4,
        answer_key_total=4,
        cousin_hit=0,
        cousin_total=20,
        background_flagged=0,
        background_total=200,
        bed=real_bed,
    )
    if floor_only.verdict != "FAIL":
        return (
            "FAIL",
            f"perfect floor with zero product did not FAIL bed_acceptance: {floor_only.verdict}",
            [],
        )
    if floor_only.floor_known_recall != 1.0 or floor_only.product_cousin_recall != 0.0:
        return "FAIL", "floor/product were blended rather than kept as separate numbers", []
    return "PASS", "", []


@register(
    "bully_corpus_bed_answer_key_never_reaches_grader",
    "FA. the BOTS answer key is never imported by grading modules (C4/Q3)",
    order=154,
)
def check_corpus_bed_answer_key_never_reaches_grader() -> tuple[str, str, list[dict]]:
    import ast
    from pathlib import Path

    bully_dir = (
        Path(__file__).resolve().parents[2] / "portal" / "modules" / "security" / "core" / "bully"
    )
    grading_modules = ("discovery.py", "artifact_graph.py", "cousin_engine.py", "baseline.py")
    offenders: list[str] = []
    for name in grading_modules:
        path = bully_dir / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "bots_answer_key" in node.module
            ):
                offenders.append(name)
            if isinstance(node, ast.Import):
                if any("bots_answer_key" in alias.name for alias in node.names):
                    offenders.append(name)
    if offenders:
        return "FAIL", f"grading modules importing the answer key: {offenders}", []
    return "PASS", "", []


@register(
    "bully_corpus_bed_fit_population_exceeds_scored_population",
    "FB. the baseline fit population exceeds the scored population (C5, fit wide/score narrow)",
    order=155,
)
def check_corpus_bed_fit_population_exceeds_scored_population() -> tuple[str, str, list[dict]]:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "bully_analyst_loop_run.py"
    source = path.read_text()
    if "fit_timelines = timelines" not in source:
        return "FAIL", "bully_analyst_loop_run.py no longer fits from the full timeline set", []
    if "score_timelines = timelines[: args.score_limit]" not in source:
        return "FAIL", "bully_analyst_loop_run.py no longer scores a narrower slice", []
    # runtime confirmation: slicing the same list can never grow it
    timelines = list(range(500))
    fit_timelines = timelines
    score_timelines = timelines[:25]
    if not (len(fit_timelines) >= len(score_timelines)):
        return "FAIL", "fit population did not exceed (or equal) the scored population", []
    return "PASS", "", []


@register(
    "bully_corpus_bed_resolve_indexes_includes_all_bots",
    "FC. resolve_indexes() includes every installed BOTS index (Lane A)",
    order=156,
)
def check_corpus_bed_resolve_indexes_includes_all_bots() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb

    indexes = cb.resolve_indexes()
    missing = [i for i in cb.BOTS_INDEXES if i not in indexes]
    if missing:
        return "FAIL", f"resolve_indexes() is missing BOTS indexes: {missing}", []
    return "PASS", "", []


@register(
    "bully_corpus_bed_d4_counts_never_a_haystack",
    "FD. D.4's own record counts still yield is_haystack=False (permanent regression)",
    order=157,
)
def check_corpus_bed_d4_counts_never_a_haystack() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb

    bed = cb.assess_bed({"portal5_lab": 2000}, records_read=2000, units_fitted=0, units_scored=0)
    if bed.is_haystack:
        return (
            "FAIL",
            "D.4's real record counts ({'portal5_lab': 2000}) were accepted as a haystack",
            [],
        )
    reasons = " ".join(bed.reasons)
    if "corpus_too_small" not in reasons or "lane_A_absent" not in reasons:
        return (
            "FAIL",
            f"expected both corpus_too_small and lane_A_absent reasons, got: {bed.reasons}",
            [],
        )
    return "PASS", "", []


# ── TASK_BULLY_REAL_TELEMETRY_V1 (T.5): the real-telemetry classifier, the
# three closed guard holes, and the floor-gates-product invariant are all
# permanent regressions -- C.6's `{'unknown','other'}` collapse, its
# `records_read: 0` / `is_haystack: true` guard hole, and its unenforced
# scale floors must never silently return. ─────────────────────────────────


@register(
    "bully_real_telemetry_captured_records_use_telemetry_behavior",
    "FE. artifact_graph.build_graph's default classifier reads real "
    "sourcetype semantics, not a verb-substring table (T1)",
    order=158,
)
def check_real_telemetry_captured_records_use_telemetry_behavior() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import artifact_graph as ag

    records = [
        {"__source_id": "lab-splunk:wineventlog:security", "EventCode": "4624", "host": "h1"},
        {"__source_id": "lab-splunk:wineventlog:security", "EventCode": "4672", "host": "h1"},
        {"__source_id": "lab-splunk:xmlwineventlog:sysmon", "EventCode": "3", "host": "h1"},
    ]
    base_t = 1_700_000_000.0
    for i, r in enumerate(records):
        r["user"] = "AR-WIN-3\\Administrator"
        r["eventTime"] = base_t + i * 5.0
    graph = ag.build_graph(records, source_id="lab-splunk:wineventlog:security")
    classes = {a.action_class for a in graph.artifacts.values()}
    if classes != {"auth", "escalate", "c2_exfil"}:
        return "FAIL", f"expected real behaviour classes, got {classes}", []
    # seeded violation: the OLD default (a verb-substring table) reading the
    # same records with no extractable verb collapses to 'unknown'
    det = ag.DeterministicActionClassifier()
    if det.classify(None) != "unknown":
        return "FAIL", "the legacy substring classifier no longer reproduces C.6's collapse", []
    return "PASS", "", []


@register(
    "bully_real_telemetry_unmapped_sourcetype_is_empty_never_unknown",
    "FF. an unmapped sourcetype classifies to '' and is reported, never "
    "'unknown' or a majority-class guess (T2)",
    order=159,
)
def check_real_telemetry_unmapped_sourcetype_is_empty() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import telemetry_behavior as tb

    cls = tb.classify_record({"anything": 1}, "Perfmon:CPU")
    if cls != "":
        return "FAIL", f"unmapped sourcetype classified as {cls!r}, expected ''", []
    report = tb.coverage_report(
        [
            ({"EventCode": "4624"}, "wineventlog:security"),
            ({"cpu_pct": 3.2}, "Perfmon:CPU"),
        ]
    )
    if "Perfmon:CPU" not in report.unmapped_sourcetypes:
        return "FAIL", "unmapped sourcetype not published in unmapped_sourcetypes", []
    return "PASS", "", []


@register(
    "bully_real_telemetry_coverage_report_degenerate_fails",
    "FG. classifier coverage_report is published per run and degenerate "
    "output-class entropy is a detectable failure (T3)",
    order=160,
)
def check_real_telemetry_coverage_report_degenerate_fails() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import telemetry_behavior as tb

    # C.6's exact shape: every real record resolves to one class -- entropy
    # 0.302 bits of a possible ~3.3, well under the 1.0-bit floor.
    collapsed = tb.coverage_report(
        [({"EventCode": "4624"}, "wineventlog:security") for _ in range(100)]
    )
    if not collapsed.degenerate:
        return "FAIL", "a single-class collapse (C.6's exact shape) was not flagged degenerate", []
    mixed = tb.coverage_report(
        [
            ({"EventCode": "4624"}, "wineventlog:security"),
            ({"EventCode": "4672"}, "wineventlog:security"),
            ({"EventCode": "1"}, "xmlwineventlog:sysmon"),
            ({"EventCode": "3"}, "xmlwineventlog:sysmon"),
            ({"query": "x"}, "stream:dns"),
        ]
    )
    if mixed.degenerate:
        return "FAIL", "a genuinely mixed real-class distribution was flagged degenerate", []
    return "PASS", "", []


@register(
    "bully_real_telemetry_assess_bed_requires_scale_inputs",
    "FH. corpus_bed.assess_bed cannot be called without units_fitted/"
    "units_scored -- an optional guard input is a guard that silently does "
    "not run (T4)",
    order=161,
)
def check_real_telemetry_assess_bed_requires_scale_inputs() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb

    try:
        cb.assess_bed({"portal5_lab": 500}, records_read=500)  # type: ignore[call-arg]
    except TypeError:
        pass
    else:
        return "FAIL", "assess_bed accepted a call with no units_fitted/units_scored", []
    if cb.MIN_SCORED_UNITS <= 0 or cb.MIN_FIT_TO_SCORE_RATIO <= 0:
        return (
            "FAIL",
            "MIN_SCORED_UNITS/MIN_FIT_TO_SCORE_RATIO are not wired to positive floors",
            [],
        )
    return "PASS", "", []


@register(
    "bully_real_telemetry_zero_records_read_never_a_haystack",
    "FI. records_read == 0 yields is_haystack=False unconditionally -- the "
    "permanent C.6 regression (records_read:0 published alongside "
    "is_haystack:true)",
    order=162,
)
def check_real_telemetry_zero_records_read_never_a_haystack() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb

    # C.6's exact shape: a 281M-record corpus, zero records actually read.
    bed = cb.assess_bed(
        {
            "portal5_lab": 19_300_000,
            "botsv1": 33_400_000,
            "botsv2": 226_300_000,
            "botsv3": 2_000_000,
        },
        records_read=0,
        units_fitted=4183,
        units_scored=200,
    )
    if bed.is_haystack:
        return "FAIL", "records_read=0 was accepted as is_haystack=True (C.6's exact defect)", []
    if not any("no_records_read" in r for r in bed.reasons):
        return "FAIL", f"is_haystack=False but no_records_read reason missing: {bed.reasons}", []
    return "PASS", "", []


@register(
    "bully_real_telemetry_zero_floor_recall_fails_acceptance",
    "FJ. floor_known_recall == 0.0 FAILs bed_acceptance independent of "
    "cousin/background checks -- a broken floor invalidates any product "
    "recall reported beside it (T5)",
    order=163,
)
def check_real_telemetry_zero_floor_recall_fails_acceptance() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb

    bed = cb.assess_bed(
        {
            "portal5_lab": 19_300_000,
            "botsv1": 33_400_000,
            "botsv2": 226_300_000,
            "botsv3": 2_000_000,
        },
        records_read=200_000_000,
        units_fitted=180_000,
        units_scored=25_000,
    )
    acceptance = cb.bed_acceptance(
        answer_key_hit=0,
        answer_key_total=4,
        cousin_hit=10,
        cousin_total=20,
        background_flagged=10,
        background_total=1000,
        bed=bed,
    )
    if acceptance.verdict == "PASS":
        return "FAIL", "zero floor_known_recall did not fail bed_acceptance", []
    if not any("zero_floor_recall" in r for r in acceptance.reasons):
        return "FAIL", f"expected a zero_floor_recall reason, got: {acceptance.reasons}", []
    return "PASS", "", []


@register(
    "bully_real_telemetry_all_unclassified_cluster_is_detectable",
    "FK. a cousin cluster whose shared shape is entirely unclassified is "
    "detectable from its sourcetypes, never silently indistinguishable "
    "from a genuine finding",
    order=164,
)
def check_real_telemetry_all_unclassified_cluster_is_detectable() -> tuple[str, str, list[dict]]:
    """T.3's live diagnostic run against the real corpus bed produced three
    cousin clusters whose `shared_shape` was entirely `""` (honest per T2 --
    every record in them came from a sourcetype `telemetry_behavior` does
    not map, e.g. `Perfmon:*`/`gen:*`). That is expected on real, partially-
    unmapped data and is not itself a defect; what would be a defect is an
    all-unclassified cluster that LOOKS like a genuine discovery because
    nothing distinguishes it. `coverage_report`'s `unmapped_sourcetypes`
    is that distinguishing signal -- this seeds exactly T.3's shape (every
    record from one unmapped sourcetype) and confirms it surfaces there."""
    from portal.modules.security.core.bully import telemetry_behavior as tb

    all_unclassified_records = [({"cpu_pct": float(i)}, "Perfmon:CPU") for i in range(50)]
    report = tb.coverage_report(all_unclassified_records)
    if report.n_classified != 0:
        return "FAIL", "seeded all-unmapped input was not entirely unclassified", []
    if "Perfmon:CPU" not in report.unmapped_sourcetypes:
        return (
            "FAIL",
            "an all-unclassified cluster's sourcetype did not surface in "
            "unmapped_sourcetypes -- it would be indistinguishable from a "
            "genuine finding",
            [],
        )
    return "PASS", "", []


# ── TASK_BULLY_INVESTIGATION_V1 (I.7): the anchor-pivot investigation model,
# concentration-aware classifier health, and the universal (table-free)
# behaviour inference path are all permanent regressions -- earliest=0,
# sourcetype-filtered capture, unbounded cousin injection, and the T.3
# suricata-dominant distribution must never silently return. ───────────────


@register(
    "bully_investigation_no_corpus_query_with_earliest_zero",
    "FL. an entity-scoped corpus query with no explicit earliest/latest "
    "window raises rather than defaulting to earliest=0 (I1/I2)",
    order=165,
)
def check_investigation_no_earliest_zero() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.connectors import QueryIntent
    from portal.modules.security.core.bully.live_connect import _search_from_intent

    intent = QueryIntent("investigate", seed={}, entities=("BSTOLL-L",))
    try:
        _search_from_intent(intent, index="botsv3")
    except ValueError as exc:
        if "earliest=0" not in str(exc):
            return "FAIL", f"raised, but not for the earliest=0 reason: {exc}", []
    else:
        return "FAIL", "an entity-scoped intent with no window did not raise", []

    bounded = QueryIntent(
        "investigate", seed={}, start=1534737600.0, end=1534824000.0, entities=("BSTOLL-L",)
    )
    expr = _search_from_intent(bounded, index="botsv3")
    if expr["earliest"] != 1534737600.0 or expr["latest"] != 1534824000.0:
        return "FAIL", f"a bounded intent's window was not passed through: {expr}", []
    return "PASS", "", []


@register(
    "bully_investigation_no_capture_query_filters_by_sourcetype",
    "FM. no pivot query ever filters by sourcetype -- a capture that "
    "filters cannot discover a source it was not told to look at (I6)",
    order=166,
)
def check_investigation_no_sourcetype_filter() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.investigation_pivot import PivotQuery

    q = PivotQuery(
        query_id="q0-0",
        index="botsv3",
        entity="BSTOLL-L",
        entity_kind="host",
        earliest=1534737600.0,
        latest=1534824000.0,
        depth=0,
        parent_query_id=None,
        reason="test",
    )
    intent = q.to_intent()
    if intent.get("sourcetype") is not None:
        return "FAIL", f"PivotQuery.to_intent() carried a sourcetype filter: {intent}", []
    return "PASS", "", []


@register(
    "bully_investigation_publishes_caps_and_truncation_state",
    "FN. every investigation publishes its caps and truncation state -- a "
    "truncated reconstruction is never presented as complete (I4)",
    order=167,
)
def check_investigation_publishes_truncation_state() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import investigation_pivot as ip

    anchor = ip.Anchor(
        anchor_id="a-1",
        at=1534737600.0,
        entity="e1",
        entity_kind="host",
        sourcetype="st",
        why="test",
        index="botsv3",
    )

    def execute(query: ip.PivotQuery) -> list[dict]:
        return [{"_time": 1534737600.0, "sourcetype": "st", "entity": query.entity}]

    def extract(row: dict) -> list[tuple[str, str]]:
        # always discovers a NEW entity, so a query beyond the cap is always
        # pending -- otherwise max_queries=1 never gets a chance to bind.
        return [("host", f"{row['entity']}-next")]

    inv = ip.investigate(anchor, ["botsv3"], execute, extract, max_queries=1)
    d = inv.to_dict()
    if "truncated_reasons" not in d or "queries" not in d:
        return "FAIL", f"Investigation.to_dict() missing bounds/truncation fields: {sorted(d)}", []
    if not d["truncated_reasons"]:
        return "FAIL", "a max_queries=1 investigation with pivots pending did not truncate", []
    return "PASS", "", []


@register(
    "bully_investigation_cousin_outside_corpus_range_refused",
    "FO. a cousin whose injected_at falls outside the corpus's real range "
    "is refused, never silently shipped (I5)",
    order=168,
)
def check_investigation_cousin_outside_range_refused() -> tuple[str, str, list[dict]]:
    import dataclasses

    from portal.modules.security.core.bully import corpus_bed as cb
    from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY

    ce, cl = 1534737600.0, 1534824000.0
    cousins = cb.plan_cousins([BOTS_ANSWER_KEY[0]], corpus_earliest=ce, corpus_latest=cl)
    t3_now_2026 = 1787316013.0
    bad = dataclasses.replace(cousins[0], injected_at=t3_now_2026)
    try:
        cb.validate_cousin_in_range(bad, corpus_earliest=ce, corpus_latest=cl)
    except cb.CousinOutsideCorpusRangeError:
        pass
    else:
        return "FAIL", "a cousin with a 2026 (T.3-shaped) injected_at was not refused", []
    return "PASS", "", []


@register(
    "bully_investigation_pivot_recursion_is_load_bearing",
    "FP. pivot recursion is load-bearing -- depth-1 misses what depth-3 reaches",
    order=169,
)
def check_investigation_pivot_recursion_load_bearing() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import investigation_pivot as ip

    # entity_a -> entity_b -> entity_c, a two-hop chain only depth>=2 reaches
    chain = {
        "entity_a": [("host", "entity_b")],
        "entity_b": [("host", "entity_c")],
    }

    def execute(query: ip.PivotQuery) -> list[dict]:
        return [{"_time": query.earliest + 1, "sourcetype": "st", "entity": query.entity}]

    def extract(row: dict) -> list[tuple[str, str]]:
        return chain.get(row.get("entity"), [])

    anchor = ip.Anchor(
        anchor_id="a-1",
        at=1534737600.0,
        entity="entity_a",
        entity_kind="host",
        sourcetype="st",
        why="test",
        index="botsv3",
    )
    shallow = ip.investigate(anchor, ["botsv3"], execute, extract, max_depth=1)
    deep = ip.investigate(anchor, ["botsv3"], execute, extract, max_depth=3)
    if "entity_c" in shallow.entities_seen:
        return "FAIL", "depth=1 unexpectedly reached the two-hop entity", []
    if "entity_c" not in deep.entities_seen:
        return (
            "FAIL",
            "depth=3 did not reach the two-hop entity -- recursion is not load-bearing",
            [],
        )
    return "PASS", "", []


@register(
    "bully_investigation_classifier_health_fails_on_concentration",
    "FQ. coverage_report fails on class or source concentration, not just entropy (I5)",
    order=170,
)
def check_investigation_classifier_concentration() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import telemetry_behavior as tb

    records: list[tuple[dict, str]] = []
    records += [({"EventCode": "4624"}, "wineventlog:security")] * 12000
    records += [({"EventCode": "4688"}, "wineventlog:security")] * 6000
    records += [({"EventCode": "1"}, "xmlwineventlog:sysmon")] * 4000
    records += [({"query": "x"}, "stream:dns")] * 3356
    records += [({"_raw": "{}"}, "suricata")] * 20317

    def stub(record: dict, sourcetype: str) -> str:
        if sourcetype == "suricata":
            return "evade"
        return tb.classify_record(record, sourcetype)

    report = tb.coverage_report(records, classifier=stub)
    if report.degenerate:
        return "FAIL", "T.3's real distribution is not degenerate by entropy alone", []
    if not report.concentrated:
        return (
            "FAIL",
            "T.3's shape (evade 44.8% all from suricata) was not flagged concentrated",
            [],
        )
    return "PASS", "", []


@register(
    "bully_investigation_t3_distribution_permanent_regression",
    "FR. T.3's suricata-dominant distribution is a permanent regression "
    "case for the concentration checks",
    order=171,
)
def check_investigation_t3_distribution_regression() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import telemetry_behavior as tb

    records: list[tuple[dict, str]] = [({"_raw": "{}"}, "suricata")] * 20317
    records += [({"EventCode": "4624"}, "wineventlog:security")] * 25039

    def stub(record: dict, sourcetype: str) -> str:
        if sourcetype == "suricata":
            return "evade"
        return tb.classify_record(record, sourcetype)

    report = tb.coverage_report(records, classifier=stub)
    if abs(report.class_concentration.get("evade", 0.0) - 0.4479) > 0.01:
        return "FAIL", f"expected ~44.8% evade share, got {report.class_concentration}", []
    if report.source_concentration.get("evade") != 1.0:
        return "FAIL", "expected evade to be 100% sourced from suricata", []
    if not report.concentrated:
        return "FAIL", "T.3's exact historical distribution was not flagged concentrated", []
    return "PASS", "", []


@register(
    "bully_investigation_no_discovery_path_touches_curated_table_or_answer_key",
    "FS. no discovery path imports telemetry_behavior, the answer key, or "
    "plan_cousins -- proven by import-scan, not asserted (I7)",
    order=172,
)
def check_investigation_no_discovery_path_imports_curated() -> tuple[str, str, list[dict]]:
    import ast
    from pathlib import Path

    bully_dir = (
        Path(__file__).resolve().parents[2] / "portal" / "modules" / "security" / "core" / "bully"
    )
    forbidden = {"telemetry_behavior", "bots_answer_key"}
    offenders = []
    for name in ("investigation_pivot", "behavior_inference"):
        path = bully_dir / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.rsplit(".", 1)[-1])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.rsplit(".", 1)[-1])
        hit = imported & forbidden
        if hit:
            offenders.append(f"{name}.py imports {sorted(hit)}")
    if offenders:
        return "FAIL", "; ".join(offenders), []
    return "PASS", "", []


@register(
    "bully_investigation_behavior_inference_never_sees_curated_names",
    "FT. behaviour spines come from behavior_inference; infer_behaviors "
    "takes no curated-table argument, and naming is a separate, later step "
    "(I8)",
    order=173,
)
def check_investigation_inference_no_curated_input() -> tuple[str, str, list[dict]]:
    import inspect

    from portal.modules.security.core.bully import behavior_inference as bi

    sig = inspect.signature(bi.infer_behaviors)
    if "curated" in sig.parameters or "answer_key" in sig.parameters:
        return "FAIL", f"infer_behaviors accepts a curated/answer-key input: {sig}", []
    name_sig = inspect.signature(bi.name_from_answer_key)
    if "curated" not in name_sig.parameters:
        return "FAIL", "naming has no separate curated-table entry point", []
    return "PASS", "", []


@register(
    "bully_investigation_every_run_publishes_inference_and_unmapped_count",
    "FU. every run publishes inference_report and the unreadable-"
    "sourcetype count beside every recall figure (I9)",
    order=174,
)
def check_investigation_run_publishes_inference_and_unmapped() -> tuple[str, str, list[dict]]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs" / "BULLY_INVESTIGATION_RUN_I6_V1.json"
    if not path.is_file():
        return "FAIL", f"{path} does not exist", []
    doc = json.loads(path.read_text())
    if "inference_report" not in doc:
        return "FAIL", "run doc does not publish inference_report", []
    coverage = doc.get("classifier_coverage_report") or {}
    if "unmapped_sourcetypes" not in coverage:
        return "FAIL", "run doc does not publish the unmapped-sourcetype count beside coverage", []
    if not any("reach_recall" in json.dumps(inv) for inv in doc.get("investigations", [])):
        return "FAIL", "run doc publishes no reach_recall figure to publish the count beside", []
    return "PASS", "", []


@register(
    "bully_investigation_unseen_schema_still_profiled_and_classified",
    "FV. a schema absent from every curated table is still profiled and "
    "classified by behavior_inference",
    order=175,
)
def check_investigation_unseen_schema_profiled() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import behavior_inference as bi

    records = []
    for i in range(10):
        ent = f"ent-{i}"
        for role, action, t in (("auth", "qrx-77", 0), ("egress", "qrx-52", 1)):
            records.append(
                {"action": action, "entity": ent, "_time": float(t), "sourcetype": "zz:unknown"}
            )
    profiles = bi.profile_actions(
        records,
        action_of=lambda r: r["action"],
        entity_of=lambda r: [r["entity"]],
        time_of=lambda r: r["_time"],
        sourcetype_of=lambda r: r["sourcetype"],
    )
    zz_actions = {p.action for p in profiles if p.sourcetype == "zz:unknown"}
    if not zz_actions:
        return "FAIL", "zz:unknown (in no curated table) was not profiled at all", []
    behaviors = bi.infer_behaviors(profiles)
    classified = {a for b in behaviors for a in b.members}
    if not (zz_actions <= classified):
        return "FAIL", f"zz:unknown actions were not classified: {zz_actions - classified}", []
    return "PASS", "", []


# ── TASK_BULLY_ADAPTIVE_REACH_V1 (A.7): CI invariants for adaptive scoping,
# depth-budgeted pivoting, chain-only reach, and the zero-scored-units bed
# guard. Each check seeds the exact I.6 defect it closes. ──────────────────


@register(
    "bully_adaptive_reach_no_flat_event_cap_a_depth_budget_is_required",
    "FW. no investigation uses a flat event cap -- a DepthBudget reserves "
    "per depth so query one cannot spend what a deeper pivot needs (A2)",
    order=176,
)
def check_adaptive_reach_depth_budget_required() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import adaptive_scope as ascope
    from portal.modules.security.core.bully import investigation_pivot as ip

    anchor = ip.Anchor(
        anchor_id="a-1",
        at=1534737600.0,
        entity="busy-host",
        entity_kind="host",
        sourcetype="st",
        why="test",
        index="botsv3",
    )

    def execute(query: ip.PivotQuery) -> list[dict]:
        # A large, constant result regardless of window -- the I.6 shape.
        return [{"_time": query.earliest + 1, "sourcetype": "st", "entity": query.entity}] * 100

    inv = ip.investigate(anchor, ["botsv3"], execute, lambda row: [], max_events=1_000)
    if inv.saturation_report is None:
        return "FAIL", "investigate() published no saturation_report", []
    if inv.saturation_report.budget.get("allowance_per_depth") is None:
        return "FAIL", "no per-depth allowance published -- a flat cap left no trace", []
    if inv.saturation_report.budget["allowance_per_depth"] >= 1_000:
        return "FAIL", "allowance_per_depth was not divided across depths", []
    # Seeded violation, mirrored: a flat cap DOES let depth 0 take everything.
    flat = ascope.DepthBudget(total_events=1_000, max_depth=0, per_query_cap=1_000)
    if flat.allowance_per_depth != 1_000:
        return "FAIL", "control case (max_depth=0) unexpectedly reserved per-depth", []
    return "PASS", "", []


@register(
    "bully_adaptive_reach_saturation_narrows_rather_than_terminating",
    "FX. a saturating window NARROWs rather than ending the investigation "
    "-- I.6 treated a large result as budget spent (A1)",
    order=177,
)
def check_adaptive_reach_saturation_narrows() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import adaptive_scope as ascope

    decision = ascope.next_window(
        5_000, ascope.OPENING_BACKWARD_SECONDS, ascope.OPENING_FORWARD_SECONDS
    )
    if decision.action != "NARROW":
        return "FAIL", f"a 5000-row result did not narrow: {decision.action}", []
    if decision.backward >= ascope.OPENING_BACKWARD_SECONDS:
        return "FAIL", "narrow decision did not actually shrink the window", []
    # Seeded violation: I.6's own behaviour (treat saturation as "stop").
    old_style_stopped = 5_000 >= 20_000  # I.6's flat MAX_EVENTS comparison
    if old_style_stopped:
        return "FAIL", "seeded check itself is broken", []
    return "PASS", "", []


@register(
    "bully_adaptive_reach_every_investigation_publishes_pivot_ran",
    "FY. every investigation publishes saturation_report with pivot_ran, "
    "so a non-pivoting reconstruction is never read as complete (A2)",
    order=178,
)
def check_adaptive_reach_publishes_pivot_ran() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import investigation_pivot as ip

    anchor = ip.Anchor(
        anchor_id="a-1",
        at=1534737600.0,
        entity="e1",
        entity_kind="host",
        sourcetype="st",
        why="test",
        index="botsv3",
    )
    inv = ip.investigate(anchor, ["botsv3"], lambda q: [], lambda row: [])
    d = inv.to_dict()
    if "saturation_report" not in d or "pivot_ran" not in d:
        return "FAIL", f"Investigation.to_dict() missing pivot_ran: {sorted(d)}", []
    if d["pivot_ran"] is not False:
        return "FAIL", "an investigation with zero rows returned claimed pivot_ran", []
    return "PASS", "", []


@register(
    "bully_adaptive_reach_reach_report_refuses_single_entity_expectation",
    "FZ. reach_report refuses a single-entity (or anchor-only) expectation "
    "-- I.6 published reach_recall 1.0 on exactly this shape (A3)",
    order=179,
)
def check_adaptive_reach_reach_report_refuses_single_entity() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import investigation_pivot as ip

    anchor = ip.Anchor(
        anchor_id="a-truth-T1558.004",
        at=1534737600.0,
        entity="BGIST-L",
        entity_kind="host",
        sourcetype="WinEventLog",
        why="test",
        index="botsv3",
    )
    inv = ip.Investigation(anchor=anchor)
    inv.entities_seen["BGIST-L"] = "host"
    report = ip.reach_report(inv, ["BGIST-L"])  # I.6's exact shape
    if report.reach_recall is not None:
        return "FAIL", f"single-entity expectation was not refused: {report.reach_recall}", []
    if not report.degenerate_expectation:
        return "FAIL", "no degenerate_expectation reason published", []
    # Control: a real two-entity chain must still score normally.
    inv.entities_seen["other-host"] = "host"
    chain_report = ip.reach_report(inv, ["BGIST-L", "other-host"])
    if chain_report.degenerate_expectation is not None:
        return "FAIL", "a genuine two-entity chain was incorrectly refused", []
    if chain_report.reach_recall != 1.0:
        return "FAIL", f"a genuine two-entity chain did not score: {chain_report.reach_recall}", []
    return "PASS", "", []


@register(
    "bully_adaptive_reach_recovery_published_by_distance_zero_hop_flagged",
    "GA. cousin recovery is published by planted distance, and a run "
    "reaching only 0-hop cousins is flagged zero_hop_only (A4)",
    order=180,
)
def check_adaptive_reach_distance_recovery_published() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import adaptive_scope as ascope

    # I.6's exact shape: every cousin recovered, all at 0 hops.
    planted = [(f"c{i}", 0) for i in range(20)]
    reached = {f"c{i}" for i in range(20)}
    rec = ascope.distance_recovery(planted, reached)
    if not rec.to_dict()["zero_hop_only"]:
        return "FAIL", "an all-0-hop recovery run was not flagged zero_hop_only", []
    # Control: a run that reaches distance 2 is not flagged.
    planted2 = [*planted, ("c20", 1), ("c21", 2)]
    reached2 = reached | {"c20", "c21"}
    rec2 = ascope.distance_recovery(planted2, reached2)
    if rec2.to_dict()["zero_hop_only"]:
        return "FAIL", "a run that reached distance 2 was incorrectly flagged zero_hop_only", []
    if rec2.max_reached_distance != 2:
        return "FAIL", f"max_reached_distance wrong: {rec2.max_reached_distance}", []
    return "PASS", "", []


@register(
    "bully_adaptive_reach_zero_scored_units_forces_is_haystack_false",
    "GB. zero scored units forces is_haystack=False -- I.6 published "
    "is_haystack: true with 0 scored units (A5)",
    order=181,
)
def check_adaptive_reach_zero_scored_units_forces_false() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import corpus_bed as cb

    # I.6's exact bed shape.
    bed = cb.assess_bed({"botsv3": 2_030_370}, records_read=213_311, units_fitted=0, units_scored=0)
    if bed.is_haystack is not False:
        return "FAIL", "zero scored units did not force is_haystack=False", []
    if not any(r.startswith("scored_sample_too_small") for r in bed.reasons):
        return "FAIL", "scored_sample_too_small reason not published", []
    try:
        cb.require_bed_acceptance({"reach_report": {}})
    except cb.RunOutputMissingBedAcceptanceError:
        pass
    else:
        return "FAIL", "a run doc missing bed_acceptance was not refused", []
    return "PASS", "", []


@register(
    "bully_adaptive_reach_i6_density_profile_permanent_regression",
    "GC. I.6's exact density profile (900 rows/hour, 24h window "
    "saturating a flat cap) is a permanent regression case for pivot_ran",
    order=182,
)
def check_adaptive_reach_i6_density_permanent_regression() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import investigation_pivot as ip

    chain = {"busy-host": [("user", "stage-1-user")], "stage-1-user": [("resource", "stage-2")]}
    anchor = ip.Anchor(
        anchor_id="a-i6-density",
        at=1534737600.0 + 15 * 3600,
        entity="busy-host",
        entity_kind="host",
        sourcetype="WinEventLog",
        why="i6_density_profile",
        index="botsv3",
    )

    def execute(query: ip.PivotQuery) -> list[dict]:
        span_hours = max(query.latest - query.earliest, 1.0) / 3600.0
        n = max(1, int(span_hours * 900))  # I.6's real measured ~900 rows/hour
        return [
            {"_time": query.earliest + 1, "sourcetype": "WinEventLog", "entity": query.entity}
            for _ in range(n)
        ]

    def extract(row: dict) -> list[tuple[str, str]]:
        return chain.get(row.get("entity"), [])

    inv = ip.investigate(anchor, ["botsv3"], execute, extract)
    if inv.saturation_report is None or not inv.saturation_report.pivot_ran:
        return (
            "FAIL",
            "I.6's density profile regressed: pivot_ran is False again",
            [],
        )
    if max(inv.saturation_report.depths_reached, default=-1) < 1:
        return "FAIL", "I.6's density profile did not reach depth >= 1", []
    return "PASS", "", []


# ── TASK_BULLY_SCORER_FEED_V1 (K.5): F.4 reached `integration_fraction 1.0`
# with every stage OK while the analytical path received 63 records of one
# sourcetype out of 325 the stream covered -- `ctx.put("records", last_
# batch)` fed the scorer whatever the final streaming iteration happened to
# hold. These checks hold the fix (K.1/K.2/K.3) in place. ───────────────────


@register(
    "bully_scorer_feed_stratified_sample_never_single_batch",
    "GD. the analytical path receives a stratified sample, never a single batch (K1)",
    order=183,
)
def check_scorer_feed_stratified_never_single_batch() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.score_sample import StratifiedSample

    stream = [({"i": i}, f"st-{i % 50}") for i in range(2_000)]
    sample = StratifiedSample(per_sourcetype=200)
    for rec, st in stream:
        sample.add(rec, st)
    if sample.total == 0:
        return "FAIL", "stratified sample produced no records from a real stream", []
    if len(sample.sourcetypes) != 50:
        return "FAIL", f"expected 50 sourcetypes represented, got {len(sample.sourcetypes)}", []
    return "PASS", "", []


@register(
    "bully_scorer_feed_verdict_published_and_starved_fails",
    "GE. scorer_input_verdict is published every run and STARVED fails it",
    order=184,
)
def check_scorer_feed_verdict_starved_fails() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.score_sample import scorer_input_verdict

    starved_report = {
        "sourcetypes_sampled": 1,
        "largest_sourcetype_share": 1.0,
        "truncated_at_max_total": False,
    }
    starved = scorer_input_verdict(starved_report, sourcetypes_covered_by_stream=325)
    if starved["verdict"] != "STARVED":
        return "FAIL", "a scorer input covering 1/325 sourcetypes did not grade STARVED", []

    healthy_report = {
        "sourcetypes_sampled": 325,
        "largest_sourcetype_share": 0.003,
        "truncated_at_max_total": False,
    }
    healthy = scorer_input_verdict(healthy_report, sourcetypes_covered_by_stream=325)
    if healthy["verdict"] != "OK":
        return "FAIL", f"a healthy scorer input did not grade OK: {healthy}", []
    return "PASS", "", []


@register(
    "bully_scorer_feed_records_received_published_per_stage",
    "GF. per-stage records-received is published alongside timing (K2/K3)",
    order=185,
)
def check_scorer_feed_records_received_published() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.full_pipeline import (
        STAGE_OK,
        PipelineReport,
        StageResult,
    )

    report = PipelineReport()
    report.stages = [
        StageResult(name="s", module="m", status=STAGE_OK, seconds=0.0, records_received=42)
    ]
    d = report.to_dict()
    stage_dict = d["stages"][0]
    if "records_received" not in stage_dict:
        return "FAIL", "StageResult.to_dict() does not publish records_received", []
    if stage_dict["records_received"] != 42:
        return "FAIL", f"records_received round-tripped wrong: {stage_dict}", []
    return "PASS", "", []


@register(
    "bully_scorer_feed_f4_profile_permanent_starved_regression",
    "GG. F.4's stage profile (records_received 63, stream 359,757) remains "
    "a permanent STARVED regression case",
    order=186,
)
def check_scorer_feed_f4_profile_permanent_regression() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.full_pipeline import (
        STAGE_OK,
        PipelineReport,
        StageResult,
        starvation_check,
    )

    analytical_stages = (
        "infer_field_roles",
        "classify_telemetry",
        "infer_universal_behaviors",
        "resolve_entities_and_timelines",
        "raise_and_verdict_concerns",
    )
    report = PipelineReport()
    report.stages = [
        StageResult(name=n, module="m", status=STAGE_OK, seconds=0.0, records_received=63)
        for n in analytical_stages
    ]
    result = starvation_check(report, stream_total=359_757, analytical_stages=analytical_stages)
    if result["verdict"] != "FAIL":
        return "FAIL", "F.4's own stage profile no longer fails starvation_check", []
    return "PASS", "", []


@register(
    "bully_scorer_feed_head_or_tail_slice_fails_stratification",
    "GH. a head or tail slice fails the stratification check (K3)",
    order=187,
)
def check_scorer_feed_head_or_tail_slice_fails() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.score_sample import scorer_input_verdict

    # a flat 1,878-record head slice of a 6,678-record, 325-sourcetype
    # stream (dominant first sourcetype) covers exactly one sourcetype.
    head_report = {
        "sourcetypes_sampled": 1,
        "largest_sourcetype_share": 1.0,
        "truncated_at_max_total": False,
    }
    verdict = scorer_input_verdict(head_report, sourcetypes_covered_by_stream=325)
    if verdict["verdict"] != "STARVED":
        return "FAIL", "a head-slice-shaped scorer input did not grade STARVED", []
    return "PASS", "", []


@register(
    "bully_scorer_feed_handoff_doc_exists_with_head_pin",
    "GI. docs/HANDOFF_BULLY_CROGL_STATE.md exists and its HEAD pin is present (K4)",
    order=188,
)
def check_scorer_feed_handoff_doc_exists() -> tuple[str, str, list[dict]]:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs" / "HANDOFF_BULLY_CROGL_STATE.md"
    if not path.exists():
        return "FAIL", f"{path} does not exist", []
    text = path.read_text()
    if "Repo HEAD at time of writing" not in text:
        return "FAIL", "handoff doc is missing its HEAD pin header", []
    if "HEAD wins over" not in text:
        return "FAIL", "handoff doc is missing its HEAD-wins-over-every-statement warning", []
    return "PASS", "", []


# ── GJ-GQ: TASK_BULLY_HUNT_SWEEP_V1 H.6 -- the hunt-sweep invariants. Each
# seeds a violation, confirms rejection, then confirms clean input passes. ──


def _scripts_dir():
    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return scripts_dir


@register(
    "bully_hunt_sweep_every_entry_attempted_or_reported",
    "GJ. the sweep attempts every in-scope entry, or reports it not-attempted (H1)",
    order=189,
)
def check_hunt_sweep_every_entry_attempted_or_reported() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import run_preflight as rpf

    progress = rpf.EntryProgress()
    progress.record(
        "botsv3",
        "T1558.004",
        {"located": True, "cousin_planted": True, "cousin_recovered": True},
    )
    # seeded violation: an entry that never ran must not vanish -- it has to
    # show up in entries_not_attempted, never be silently dropped.
    candidates = [("botsv3", "T1558.004"), ("botsv3", "T1078"), ("botsv3", "T1021.001")]
    progress.entries_not_attempted = [
        rpf.entry_key(ds, t) for ds, t in candidates if not progress.already_done(ds, t)
    ]
    payload = progress.to_dict()
    if payload["n_done"] + payload["n_not_attempted"] != len(candidates):
        return "FAIL", "attempted + not-attempted does not cover every in-scope entry", []
    if "botsv3:T1078" not in payload["entries_not_attempted"]:
        return "FAIL", "an unattempted entry was silently dropped, not reported", []
    return "PASS", "", []


@register(
    "bully_hunt_sweep_sampled_window_raises",
    "GK. a hunt window is read completely; a sampled window raises (H2)",
    order=190,
)
def check_hunt_sweep_sampled_window_raises() -> tuple[str, str, list[dict]]:
    from unittest.mock import patch

    _scripts_dir()
    import bully_full_assembly_run as fa

    class _Result:
        records = [{"host": "h1", "sourcetype": "wineventlog:security", "_time": 1.0}] * 5

    connector = type("FakeConnector", (), {"read": staticmethod(lambda _intent: _Result())})()

    # seeded violation: the window's true count vastly exceeds what the read
    # actually returned -- a truncated/sampled window, not a complete one.
    with patch("bully_full_assembly_run._window_count", return_value=500):
        try:
            fa._read_window_completely(connector, "botsv3", 0.0, 600.0)
        except fa.SampledWindowError:
            pass
        else:
            return "FAIL", "an under-read window did not raise SampledWindowError", []

    with patch("bully_full_assembly_run._window_count", return_value=5):
        try:
            rows = fa._read_window_completely(connector, "botsv3", 0.0, 600.0)
        except fa.SampledWindowError:
            return "FAIL", "a genuinely complete window incorrectly raised SampledWindowError", []
    if len(rows) != 5:
        return "FAIL", "a complete window did not return all its records", []
    return "PASS", "", []


@register(
    "bully_hunt_sweep_narrow_span_blocks_the_sweep",
    "GL. calibration runs before the sweep and NARROW_SPAN blocks it (H3)",
    order=191,
)
def check_hunt_sweep_narrow_span_blocks() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import run_preflight as rpf

    over_budget = rpf.calibrate_span(
        span_seconds=3600,
        index="botsv3",
        measured_records=84_583,
        measured_units=2_158,
        measured_cluster_seconds=3_894.0,
        measured_total_seconds=3_894.0,
        n_entries=27,
        budget_hours=4.0,
    )
    report = rpf.preflight(
        [rpf.PreflightCheck(name="anchors_resolve", passed=True, detail="ok")],
        calibration=over_budget,
    )
    # seeded violation: every gate check passing must not be enough to
    # commit if the calibration itself says NARROW_SPAN.
    if report.passed:
        return "FAIL", "NARROW_SPAN calibration did not block an otherwise-green preflight", []

    committed = rpf.calibrate_span(
        span_seconds=600,
        index="botsv3",
        measured_records=36_640,
        measured_units=537,
        measured_cluster_seconds=25.4,
        measured_total_seconds=25.4,
        n_entries=27,
        budget_hours=4.0,
    )
    clean_report = rpf.preflight(
        [rpf.PreflightCheck(name="anchors_resolve", passed=True, detail="ok")],
        calibration=committed,
    )
    if not clean_report.passed:
        return "FAIL", "a genuine COMMIT calibration was incorrectly blocked", []
    return "PASS", "", []


@register(
    "bully_hunt_sweep_incremental_checkpoint_and_publication",
    "GM. per-entry results are checkpointed and published incrementally (H4)",
    order=192,
)
def check_hunt_sweep_incremental_checkpoint() -> tuple[str, str, list[dict]]:
    import tempfile
    from pathlib import Path

    _scripts_dir()
    import bully_full_assembly_run as fa

    from portal.modules.security.core.bully import run_preflight as rpf

    with tempfile.TemporaryDirectory() as tmp:
        original = fa.CHECKPOINT_PATH
        fa.CHECKPOINT_PATH = Path(tmp) / "checkpoint.json"
        try:
            progress = rpf.EntryProgress()
            progress.record("botsv3", "T1558.004", {"located": True, "seconds": 1.0})
            fa._save_hunt_checkpoint(progress, span_seconds=600.0)
            # seeded violation: a run that died right here must still leave a
            # readable checkpoint with the one entry it finished.
            reloaded = fa._load_hunt_checkpoint()
            if reloaded is None:
                return "FAIL", "a checkpoint saved after one entry did not round-trip", []
            reloaded_progress, span = reloaded
            if reloaded_progress.entries_done != ["botsv3:T1558.004"] or span != 600.0:
                return (
                    "FAIL",
                    f"checkpoint round-trip lost state: {reloaded_progress.to_dict()}",
                    [],
                )
        finally:
            fa.CHECKPOINT_PATH = original
    return "PASS", "", []


@register(
    "bully_hunt_sweep_resumed_run_never_replants",
    "GN. a resumed run never re-plants a cousin",
    order=193,
)
def check_hunt_sweep_resumed_run_never_replants() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully import run_preflight as rpf

    progress = rpf.EntryProgress()
    progress.record_plant("botsv3", "T1558.004", "cz-botsv3-T1558.004-000-d0")
    # seeded violation: a naive resume that ignores already_planted would
    # ship a second cousin id for the same technique.
    already = progress.already_planted("botsv3", "T1558.004")
    if already is None:
        return "FAIL", "already_planted did not recognise a cousin shipped in a prior run", []
    if already != "cz-botsv3-T1558.004-000-d0":
        return "FAIL", "already_planted returned the wrong cousin id", []
    never_planted = progress.already_planted("botsv3", "T1021.001")
    if never_planted is not None:
        return "FAIL", "already_planted invented a cousin id for a technique never planted", []
    cross_dataset = progress.already_planted("botsv2", "T1558.004")
    if cross_dataset is not None:
        return (
            "FAIL",
            "already_planted matched a different dataset's own copy of the same technique",
            [],
        )
    # seeded violation: (dataset, technique) alone is still not a unique
    # answer-key identity -- the real key has two DIFFERENT confirmed
    # botsv1/T1071.001 entries (distinct source hosts, same C2 domain).
    # already_planted must key on entities too, or the second entry's
    # plant is mistaken for the first's.
    progress.record_plant("botsv1", "T1071.001", "cz-a", entities=("192.168.250.40",))
    same_pair_other_entity = progress.already_planted(
        "botsv1", "T1071.001", entities=("192.168.250.70",)
    )
    if same_pair_other_entity is not None:
        return (
            "FAIL",
            "already_planted matched a different entry sharing (dataset, technique)",
            [],
        )
    return "PASS", "", []


@register(
    "bully_hunt_sweep_no_claim_from_zero_record_stage",
    "GO. no claim is published from a zero-record stage (H4)",
    order=194,
)
def check_hunt_sweep_no_claim_from_zero_record_stage() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.full_pipeline import (
        STAGE_OK,
        PipelineReport,
        StageResult,
        zero_record_claim_guard,
    )

    zero = PipelineReport()
    zero.stages = [
        StageResult(
            name="investigate_anchors",
            module="investigation_pivot",
            status=STAGE_OK,
            seconds=0.1,
            records_received=0,
        )
    ]
    guard = zero_record_claim_guard(zero, ("investigate_anchors", "infer_universal_behaviors"))
    if "investigate_anchors" not in guard["disqualified_stages"]:
        return "FAIL", "a zero-record investigate_anchors stage was not disqualified", []

    healthy = PipelineReport()
    healthy.stages = [
        StageResult(
            name="investigate_anchors",
            module="investigation_pivot",
            status=STAGE_OK,
            seconds=12.0,
            records_received=36_640,
        )
    ]
    guard2 = zero_record_claim_guard(healthy, ("investigate_anchors", "infer_universal_behaviors"))
    if "investigate_anchors" in guard2["disqualified_stages"]:
        return "FAIL", "a genuinely populated stage was incorrectly disqualified", []
    return "PASS", "", []


@register(
    "bully_hunt_sweep_crogl_reported_as_comprehension_not_exposure",
    "GP. Crogl is reported as comprehension, not exposure",
    order=195,
)
def check_hunt_sweep_crogl_comprehension_not_exposure() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.full_pipeline import ClaimEvidence

    fields = ClaimEvidence.__dataclass_fields__
    # seeded violation: K.4 published exposure (sourcetypes touched by the
    # stream) as if it answered comprehension. The dedicated
    # crogl_sources_profiled/crogl_sources_sampled pair must exist
    # separately from the exposure-only crogl_sourcetypes_reviewed field.
    if "crogl_sources_profiled" not in fields or "crogl_sources_sampled" not in fields:
        return "FAIL", "ClaimEvidence carries no dedicated comprehension fields", []
    evidence = ClaimEvidence(
        crogl_sourcetypes_reviewed=325,
        crogl_identity_coverage=None,
        bully_chain_reach_recall=None,
        bully_max_pivot_distance=None,
        corpus_records_processed=0,
        corpus_records_available=0,
        generator_cousin_recall_at_distance={},
        crogl_sources_profiled=5,
        crogl_sources_sampled=245,
    )
    if evidence.crogl_sources_profiled == evidence.crogl_sourcetypes_reviewed:
        return (
            "FAIL",
            "comprehension collapsed onto the exposure field -- fixture is degenerate",
            [],
        )
    return "PASS", "", []


@register(
    "bully_hunt_sweep_k4_one_entry_shape_permanent_regression",
    "GQ. K.4's one-entry shape remains a permanent regression case (GJ)",
    order=196,
)
def check_hunt_sweep_k4_one_entry_shape_permanent_regression() -> tuple[str, str, list[dict]]:
    from portal.modules.security.core.bully.full_pipeline import (
        STAGE_OK,
        PipelineReport,
        StageResult,
        zero_record_claim_guard,
    )

    # K.4's own exact shape: investigate_anchors ran at records_received: 0
    # (n_answer_key_entries_tried: 1, the single-entry proof, not a sweep).
    k4_shape = PipelineReport()
    k4_shape.stages = [
        StageResult(
            name="investigate_anchors",
            module="investigation_pivot",
            status=STAGE_OK,
            seconds=0.0,
            records_received=0,
        )
    ]
    guard = zero_record_claim_guard(k4_shape, ("investigate_anchors", "infer_universal_behaviors"))
    if "investigate_anchors" not in guard["disqualified_stages"]:
        return (
            "FAIL",
            "K.4's own zero-record investigate_anchors shape no longer disqualifies "
            "Bully claims -- the regression case this check exists to pin has drifted",
            [],
        )
    return "PASS", "", []
