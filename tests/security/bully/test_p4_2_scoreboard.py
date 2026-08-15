"""P4.2 -- SCORE catch/trust/discovery axes (I-10).

Hermetic (no network, no store I/O -- pure compute over injected records).
FINAL_VALIDATION C10 SCORE: ANOMALOUS_UNCLASSIFIED is an Axis-1 catch and
the trust ordinal holds (BN); the discovery axis orders far-NEW >=
known-bad; benign false-flags typed (BQ).
"""

from __future__ import annotations

from portal.modules.security.core.bully import scoreboard


def _record(**overrides) -> dict:
    base = {
        "assessment_id": "as-1",
        "relationship": "NEW",
        "defense_response": "MISSED",
        "composite": 0.45,
        "candidate_state": None,
        "known_benign": False,
    }
    return {**base, **overrides}


def test_anomalous_unclassified_is_an_axis1_catch():
    rec = _record(relationship="ANOMALOUS_UNCLASSIFIED", defense_response="INDETERMINATE")
    scored = scoreboard.score_record(rec)
    assert scored["catch"] is True
    assert scored["trust_class"] == scoreboard.HONEST_ANOMALY


def test_different_relationship_is_not_a_catch():
    rec = _record(relationship="DIFFERENT", defense_response="COVERED")
    scored = scoreboard.score_record(rec)
    assert scored["catch"] is False


def test_trust_ordinal_ordering_preserved():
    promoted = scoreboard.score_record(
        _record(relationship="SAME", defense_response="COVERED", candidate_state="PROMOTED")
    )
    anomaly = scoreboard.score_record(_record(relationship="ANOMALOUS_UNCLASSIFIED"))
    killed = scoreboard.score_record(
        _record(relationship="SAME", defense_response="MISSED", candidate_state="KILLED")
    )
    assert promoted["trust_class"] == scoreboard.CONFIRMED_CORRECT
    assert anomaly["trust_class"] == scoreboard.HONEST_ANOMALY
    assert killed["trust_class"] == scoreboard.CONFIRMED_WRONG
    assert promoted["trust_rank"] > anomaly["trust_rank"] > killed["trust_rank"]


def test_discovery_weighting_monotonic_in_distance():
    near = scoreboard.score_record(
        _record(relationship="SIMILAR", defense_response="NEAR_MISS", composite=0.20)
    )
    far = scoreboard.score_record(
        _record(relationship="NEW", defense_response="MISSED", composite=0.55)
    )
    assert far["discovery_value"] > near["discovery_value"]

    a = scoreboard.score_record(
        _record(relationship="NEW", defense_response="MISSED", composite=0.40)
    )
    b = scoreboard.score_record(
        _record(relationship="NEW", defense_response="MISSED", composite=0.58)
    )
    assert b["discovery_value"] > a["discovery_value"]


def test_far_new_scores_at_least_as_high_as_known_bad():
    """Principle: 'far-NEW >= known-bad'. SAME (known-bad) never scores on
    the discovery axis -- 0.0 for every distance -- so this holds for any
    NEW/SIMILAR discovery-product record, trivially and monotonically."""
    known_bad = scoreboard.score_record(
        _record(relationship="SAME", defense_response="MISSED", composite=0.05)
    )
    far_new = scoreboard.score_record(
        _record(relationship="NEW", defense_response="MISSED", composite=0.59)
    )
    assert known_bad["discovery_value"] == 0.0
    assert far_new["discovery_value"] >= known_bad["discovery_value"]


def test_anomalous_has_a_discovery_floor():
    rec = scoreboard.score_record(
        _record(
            relationship="ANOMALOUS_UNCLASSIFIED", defense_response="INDETERMINATE", composite=0.05
        )
    )
    assert rec["discovery_value"] >= scoreboard._ANOMALY_DISCOVERY_FLOOR


def test_benign_false_flag_typing_preserved():
    confirmed_on_benign = scoreboard.score_record(
        _record(relationship="SAME", defense_response="COVERED", known_benign=True)
    )
    anomaly_on_benign = scoreboard.score_record(
        _record(relationship="ANOMALOUS_UNCLASSIFIED", known_benign=True)
    )
    correct_silence = scoreboard.score_record(
        _record(relationship="DIFFERENT", defense_response="COVERED", known_benign=True)
    )
    assert confirmed_on_benign["false_flag"] is True
    assert confirmed_on_benign["false_flag_kind"] == scoreboard.CONFIRMED_ON_BENIGN
    assert anomaly_on_benign["false_flag"] is True
    assert anomaly_on_benign["false_flag_kind"] == scoreboard.ANOMALY_ON_BENIGN
    assert correct_silence["false_flag"] is False
    assert correct_silence["false_flag_kind"] is None
    # A benign subject is never scored on trust/discovery -- data absence is
    # reported, not faked.
    assert confirmed_on_benign["trust_class"] is None
    assert confirmed_on_benign["discovery_value"] == 0.0


def test_update_aggregates_hunt_row_and_report_hunt_scope_passthrough():
    records = [
        _record(assessment_id="as-1", relationship="ANOMALOUS_UNCLASSIFIED"),
        _record(assessment_id="as-2", relationship="DIFFERENT", defense_response="COVERED"),
        _record(
            assessment_id="as-3",
            relationship="SAME",
            defense_response="COVERED",
            candidate_state="PROMOTED",
        ),
    ]
    row = scoreboard.update("hunt-1", records)
    assert row["hunt_id"] == "hunt-1"
    assert row["n_records"] == 3
    assert row["catch_count"] == 2  # ANOMALOUS + SAME-promoted; DIFFERENT is not a catch
    assert row["false_flag_count"] == 0

    hunt_report = scoreboard.report("hunt", [row])
    assert hunt_report["scope"] == "hunt"
    assert hunt_report["hunt_id"] == "hunt-1"


def test_report_series_aggregates_across_hunts():
    row_a = scoreboard.update("hunt-A", [_record(assessment_id="as-1")])
    row_b = scoreboard.update(
        "hunt-B",
        [_record(assessment_id="as-2", relationship="DIFFERENT", defense_response="COVERED")],
    )
    series = scoreboard.report("series", [row_a, row_b])
    assert series["scope"] == "series"
    assert series["n_hunts"] == 2
    assert series["n_records"] == 2


def test_report_empty_rows_is_honest_none_not_zero():
    series = scoreboard.report("series", [])
    assert series["n_hunts"] == 0
    assert series["catch_rate"] is None
    assert series["trust_mean_rank"] is None


# ── store assembly (scoreboard_records_for_hunt) ─────────────────────────────


def test_store_assembles_scoreboard_records_from_a_real_graded_hunt(tmp_path):
    """The scoreboard row store.py assembles from a real LOOP-graded hunt
    (test_p1_7_orchestrator.py's own synthetic-lab fixtures) feeds cleanly
    into scoreboard.update -- proves the store<->scoreboard join, not just
    hand-built dicts."""
    from portal.modules.security.core.bully import orchestrator as orch
    from portal.modules.security.core.bully.investigation import InvestigationResult
    from portal.modules.security.core.bully.organ import Organ
    from portal.modules.security.core.bully.store import Store
    from portal.modules.security.core.episode import Episode

    store = Store(tmp_path / "hunt_state.db")
    organ = Organ(store=store, db_path=tmp_path / "hunt_memory")
    organ._embed = lambda texts: [[float((hash(t) >> i) % 7) for i in range(8)] for t in texts]

    store.hunt_create(
        hunt_id="hunt-score-1",
        objective="prove scoreboard join",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire("hunt-score-1", owner="operator:alice")

    def _lab_driver(target_cell, *, dry_run):
        return Episode(
            episode_id="ep-20260101T000000Z-scn-abcd1234",
            scenario="lateral-movement-wmi",
            target_host="host-1",
            started_at=0.0,
            red_status="RED_LANDED",
            telemetry_status="TELEMETRY_INDEXED",
            detection_status="DETECTION_CONFIRMED",
        )

    def _inv_arm(episode, *, models, dry_run=False):
        return InvestigationResult(
            verdict="CONFIRMED",
            technique_ids=("T1021.002",),
            grounded_technique_ids=("T1021.002",),
            dropped_technique_ids=(),
            contradicted_technique_ids=(),
            reasoning="mocked",
            match_grade="EXACT",
            evidence=("wmic process call create observed",),
        )

    orch.run_hunt_iteration(
        store,
        organ,
        hunt_id="hunt-score-1",
        actor="operator:alice",
        neighborhood="lab-default",
        lab_driver=_lab_driver,
        investigation_arm=_inv_arm,
    )

    records = store.scoreboard_records_for_hunt("hunt-score-1")
    assert len(records) == 1
    row = scoreboard.update("hunt-score-1", records)
    assert row["n_records"] == 1
    assert row["hunt_id"] == "hunt-score-1"

    organ.close()
    store.close()
