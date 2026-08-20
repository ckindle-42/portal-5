"""E.4 -- remarkability measures content, not a fit/score level gap (RC3).
TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1."""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl


def _unit(verbs: list[str], entity: str) -> ag.GradeableUnit:
    records = [
        {"eventName": v, "user": entity, "eventTime": 1_700_000_000.0 + i * 40.0}
        for i, v in enumerate(verbs)
    ]
    graph = ag.build_graph(records)
    level = "L1_ARTIFACT" if len(records) < 2 else "L4_WINDOW"
    return next(u for u in ag.enumerate_units(graph) if u.level == level)


def test_no_level_token_in_feature_vocabulary() -> None:
    unit = _unit(["AssumeRole", "ListBuckets", "AttachUserPolicy"], "attacker")
    tokens = bl._feature_tokens(unit)
    assert not any(t.startswith("level=") for t in tokens)


def test_fitting_n_copies_and_scoring_the_identical_unit_is_near_zero() -> None:
    """The proof from the RC3 review: fit 100 copies of a unit, score that
    identical unit -> the only configuration that should return ~0.0.
    Under the old `level=`/cross-level tokens this returned ~0.7."""
    unit = _unit(["AssumeRole", "ListBuckets", "AttachUserPolicy"], "attacker")
    model = bl.NormalBaseline(environment_id="e")
    model.fit([unit] * 100)
    assert model.remarkability(unit) < 0.05


def test_cross_level_scoring_is_honest_zero_not_a_silent_floor() -> None:
    """RC3's actual defect: fit L1_ARTIFACT, score L4_WINDOW. Statistics are
    partitioned by level, so a level with nothing fitted scores 0.0
    honestly -- never a content-independent ~0.95 floor."""
    l1_units = [_unit(["ListBuckets"], f"u{i}") for i in range(200)]
    model = bl.NormalBaseline(environment_id="e")
    model.fit(l1_units)

    l4_unit = _unit(
        ["AssumeRole", "ListBuckets", "AttachUserPolicy", "PutObject", "GetObject", "DeleteBucket"],
        "attacker",
    )
    assert model.fitted_units_at("L4_WINDOW") == 0
    assert model.remarkability(l4_unit) == 0.0
    assert not model.is_remarkable(l4_unit)


def test_same_level_scoring_measures_content_not_level_gap() -> None:
    """A benign control fitted and scored at the SAME level (perfectly
    clean data, RC3's misdiagnosed invictus case) must score low -- proving
    the fix generalizes beyond the single-identical-unit case."""
    model = bl.NormalBaseline(environment_id="e")
    benign_cycle = ["ListBuckets", "GetObject", "DescribeInstances"]
    model.fit([_unit(benign_cycle, f"u{i}") for i in range(100)])

    probe = _unit(benign_cycle, "u-probe")
    assert model.remarkability(probe) < 0.3
    assert not model.is_remarkable(probe)


def test_baseline_fit_partitions_by_level() -> None:
    model = bl.NormalBaseline(environment_id="e")
    model.fit([_unit(["ListBuckets"], f"u{i}") for i in range(30)])
    model.fit([_unit(["ListBuckets", "GetObject"], f"combo-{i}") for i in range(10)])
    assert model.fitted_units_at("L1_ARTIFACT") == 30
    assert model.fitted_units_at("L4_WINDOW") == 10
    assert model.fitted_units == 40
