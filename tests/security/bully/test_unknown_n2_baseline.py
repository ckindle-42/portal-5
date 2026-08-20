"""N.2 -- the normal baseline (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl


def _routine_units(count: int) -> list[ag.GradeableUnit]:
    # Users recur (20 identities cycling) rather than being unique per
    # record: a near-unique-per-record field is a record id under
    # field-role inference (E.1/E.2), not a pivotable entity -- correctly,
    # since real routine telemetry recurs by identity.
    records = [
        {
            "eventName": "ListBuckets",
            "user": f"u{i % 20}",
            "eventTime": 1_700_000_000.0 + float(i * 10),
        }
        for i in range(count)
    ]
    graph = ag.build_graph(records)
    return [u for u in ag.enumerate_units(graph) if u.level == "L1_ARTIFACT"]


def test_routine_unit_scores_low_remarkability_after_fitting():
    fit_units = _routine_units(200)
    model = bl.NormalBaseline(environment_id="env-1")
    model.fit(fit_units)

    probe = _routine_units(1)[0]
    assert model.remarkability(probe) < 0.3
    assert not model.is_remarkable(probe)


def _benign_combinations(count: int) -> list[ag.GradeableUnit]:
    """Routine multi-step L4_WINDOW combinations (a benign browse pattern
    repeated by many different actors) -- fitted so a genuinely novel
    combination can be judged remarkable *relative to normal combinations*,
    not by an accidental fit/score level mismatch (RC3, E.4)."""
    units: list[ag.GradeableUnit] = []
    for i in range(count):
        records = [
            {
                "eventName": v,
                "user": f"benign-{i % 15}",
                "eventTime": 1_700_050_000.0 + i * 1000.0 + step * 40.0,
            }
            for step, v in enumerate(["ListBuckets", "GetObject"])
        ]
        graph = ag.build_graph(records)
        units.append(next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW"))
    return units


def test_never_before_seen_shape_scores_high_remarkability():
    fit_units = _routine_units(200)
    model = bl.NormalBaseline(environment_id="env-1")
    model.fit(fit_units)
    model.fit(_benign_combinations(60))

    chain = [
        {"eventName": v, "user": "attacker", "eventTime": 1_700_100_000.0 + i * 40.0}
        for i, v in enumerate(
            [
                "AssumeRole",
                "ListBuckets",
                "AttachUserPolicy",
                "PutObject",
                "GetObject",
                "DeleteBucket",
            ]
        )
    ]
    graph = ag.build_graph(chain)
    novel_unit = next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")

    assert model.remarkability(novel_unit) > bl.REMARKABLE_MIN_SCORE
    assert model.is_remarkable(novel_unit)


def test_empty_baseline_never_calls_anything_remarkable():
    model = bl.NormalBaseline(environment_id="env-empty")
    probe = _routine_units(1)[0]
    assert model.remarkability(probe) == 0.0
    assert not model.is_remarkable(probe)


def test_per_environment_baselines_do_not_share_state():
    a = bl.NormalBaseline(environment_id="a")
    b = bl.NormalBaseline(environment_id="b")
    a.fit(_routine_units(50))
    assert a.fitted_units == 50
    assert b.fitted_units == 0
