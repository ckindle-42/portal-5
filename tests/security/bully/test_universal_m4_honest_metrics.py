"""M.4 -- honest metrics: split cousin/novelty recall, INSUFFICIENT_VIEW
gate on neither-channel-observable relations (RC5, RC6).
TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_measurement as um
from portal.modules.security.core.bully import unit_outcome as uo

_VERBS = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]


def _unit(verbs: list[str], entity: str) -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": entity, "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = ag.build_graph(records)
    level = "L1_ARTIFACT" if len(records) < 2 else "L4_WINDOW"
    return next(u for u in ag.enumerate_units(graph) if u.level == level)


# ── RC5: neither-channel-observable is always INSUFFICIENT_VIEW ────────────


def test_novel_outcome_reports_unit_own_observability_not_a_blanket_claim() -> None:
    """The regression this fix exists for: a well-observed NOVEL unit must
    not carry what_could_not_be_seen=["shape", "vocabulary"] just because
    no anchor happened to match it."""
    model = bl.NormalBaseline(environment_id="env")
    model.fit([_unit(["ListBuckets"], f"u{i}") for i in range(50)])
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
    model.fit([_unit(benign_combo, f"benign-{i}") for i in range(50)])

    unit = _unit(attacker_verbs, "attacker")
    outcome = uo.resolve_unit_outcome(unit, [], model)
    assert outcome.outcome == "NOVEL"
    assert outcome.brief is not None
    assert outcome.brief.what_could_not_be_seen == ()


def test_concern_never_carries_both_channels_unobservable() -> None:
    """RC5: a concern (UNKNOWN_SAME/COUSIN/NOVEL) must never carry
    what_could_not_be_seen covering both channels -- that combination means
    nothing was actually seen, which is INSUFFICIENT_VIEW's job."""
    model = bl.NormalBaseline(environment_id="env")
    model.fit([_unit(["ListBuckets"], f"u{i}") for i in range(50)])
    # D.2, discovery-first: a library match alone no longer surfaces a
    # concern (D1) -- fit an unrelated benign L4_WINDOW shape so the probe's
    # own content, not a missing baseline, is what makes it remarkable.
    benign_cycle = ["ListBuckets", "GetObject", "DescribeInstances"]
    model.fit([_unit(benign_cycle[: len(_VERBS)], f"benign-{i}") for i in range(50)])
    library = anc.AnchorLibrary()
    library.load_attack_episode(
        source_id="attack_data", record={"action_sequence": _VERBS}, techniques=("T1078",)
    )
    unit = _unit(_VERBS, "attacker")
    outcome = uo.resolve_unit_outcome(unit, list(library.all()), model)
    assert outcome.outcome in uo.CONCERN_OUTCOMES
    assert outcome.brief is not None
    assert set(outcome.brief.what_could_not_be_seen) != {"shape", "vocabulary"}


def test_uncomputable_unit_still_reaches_insufficient_view() -> None:
    empty_unit = ag.GradeableUnit(
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
    model = bl.NormalBaseline(environment_id="env")
    outcome = uo.resolve_unit_outcome(empty_unit, [], model)
    assert outcome.outcome == "INSUFFICIENT_VIEW"
    assert outcome.brief is None


# ── RC6: cousin_recall and novelty_recall are separate ──────────────────────


def _pure_novel_setup() -> tuple[
    dict[str, list[ag.GradeableUnit]], dict[str, list], list, bl.NormalBaseline
]:
    """A family whose eval units match no anchor (empty library for that
    family) but are remarkable against the baseline -- pure NOVEL, zero
    library consultation."""
    model = bl.NormalBaseline(environment_id="env")
    model.fit([_unit(["ListBuckets"], f"u{i}") for i in range(50)])
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
    model.fit([_unit(benign_combo, f"benign-{i}") for i in range(50)])

    eval_units = {"family_novel": [_unit(attacker_verbs, "attacker")]}
    library_by_family: dict[str, list] = {"family_novel": []}
    full_library: list = []
    return eval_units, library_by_family, full_library, model


def test_pure_novel_population_yields_zero_cousin_recall() -> None:
    """Seeded (RC6): a run made of pure NOVEL outcomes must report
    cousin_recall 0.0 regardless of novelty_recall -- cousin_recall never
    counts a NOVEL as a match."""
    eval_units, library_by_family, full_library, model = _pure_novel_setup()
    report = um.run_leave_one_family_out(
        eval_units, library_by_family, full_library, model, benign_eval_units=[]
    )
    assert report.cousin_recall == 0.0
    assert report.novelty_recall > 0.0


def test_cousin_and_novelty_recall_reported_separately() -> None:
    eval_units, library_by_family, full_library, model = _pure_novel_setup()
    report = um.run_leave_one_family_out(
        eval_units, library_by_family, full_library, model, benign_eval_units=[]
    )
    payload = report.to_dict()
    assert "cousin_recall" in payload
    assert "novelty_recall" in payload
    assert payload["cousin_recall"] != payload["novelty_recall"]


def test_absolute_recall_published_beside_conditional() -> None:
    lib = anc.AnchorLibrary()
    anchor = lib.load_attack_episode(
        source_id="attack_data", record={"action_sequence": _VERBS}, techniques=("T1078",)
    )
    model = bl.NormalBaseline(environment_id="env")
    model.fit([_unit(["ListBuckets"], f"u{i}") for i in range(20)])

    eval_units = {"family_a": [_unit(_VERBS, "a1")]}
    # 4 datasets carried known activity for family_a; only 1 formed a unit.
    report = um.run_leave_one_family_out(
        eval_units,
        {"family_a": [anchor]},
        list(lib.all()),
        model,
        benign_eval_units=[],
        known_activity_count_by_family={"family_a": 4},
    )
    payload = report.to_dict()
    assert "absolute_recall" in payload
    assert "conditional_recall" in payload
    # absolute recall is diluted by the 3 silent (no-unit) datasets
    assert payload["absolute_recall"] <= payload["conditional_recall"]


def test_seeded_violation_no_known_activity_count_makes_absolute_equal_conditional() -> None:
    """Without known_activity_count_by_family, absolute recall degrades
    gracefully to equal conditional recall -- never a crash, never a
    fabricated denominator."""
    eval_units, library_by_family, full_library, model = _pure_novel_setup()
    report = um.run_leave_one_family_out(
        eval_units, library_by_family, full_library, model, benign_eval_units=[]
    )
    assert report.absolute_recall == report.conditional_recall
