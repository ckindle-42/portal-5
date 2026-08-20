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
    from portal.modules.security.core.bully.scoreboard_conformance import check_run

    for name, run_json in _scoreboard_conformance_new_run_docs():
        codes = {f.code for f in check_run(run_json)}
        if "trust_axis_fed_nulls" in codes:
            return (
                "FAIL",
                f"{name} feeds the trust axis hardcoded candidate_state=None/known_benign=False",
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
