"""W.1 -- the scoreboard-conformance guard (TASK_BULLY_SCOREBOARD_CONFORMANCE_V1).

Verifies the corrected diagnosis: `scoreboard.py` is unmodified and sound; the
guard catches a REPORTING-LAYER bypass -- a block labelled "scoreboard" that
isn't `scoreboard.update()`'s contract, a per-row subset that drops the
correctness fields, and a correctness axis never published at all. Seeded
against the five historical run docs (permanent regression, W5) and against a
conformant run (must PASS)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from portal.modules.security.core.bully import scoreboard as scoreboard_mod
from portal.modules.security.core.bully.scoreboard_conformance import (
    SCOREBOARD_UPDATE_CONTRACT,
    check_run,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

_HISTORICAL_RUN_DOCS = (
    "BULLY_COUSIN_RELATION_RUN_C7_V1.json",
    "BULLY_LOOP_MILESTONE_RUN_R6_V1.json",
    "BULLY_RELATE_INVESTIGATE_RUN_M3_V1.json",
    "BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json",
    "BULLY_UNKNOWN_COUSIN_RUN_M3_V1.json",
)


def _derived_update_contract() -> tuple[str, ...]:
    """Derive the real contract from `scoreboard.update()`'s own return value
    -- never re-typed from prose -- so the test can never drift from the
    module it is guarding."""
    row = scoreboard_mod.update("contract-probe-hunt", [])
    return tuple(k for k in row if k != "records")


def test_contract_matches_scoreboard_update_at_test_time():
    assert set(SCOREBOARD_UPDATE_CONTRACT) == set(_derived_update_contract())


def test_all_five_historical_runs_fail():
    for name in _HISTORICAL_RUN_DOCS:
        path = REPO_ROOT / "docs" / name
        assert path.is_file(), f"missing historical run doc: {name}"
        run_json = json.loads(path.read_text())
        findings = check_run(run_json)
        codes = {f.code for f in findings}
        assert any(f.severity == "FAIL" for f in findings), (
            f"{name} should FAIL conformance but did not"
        )
        assert "correctness_axis_not_published" in codes, (
            f"{name} should fire correctness_axis_not_published -- "
            f"none of the five runs ever published trust_mean_rank/false_flag_count"
        )


def test_conformant_run_passes():
    conformant = {
        "scoreboard": {
            "hunt_id": "hunt-x",
            "n_records": 2,
            "catch_count": 1,
            "catch_rate": 0.5,
            "trust_mean_rank": 1.5,
            "discovery_total": 0.8,
            "discovery_mean": 0.4,
            "false_flag_count": 0,
        },
        "per_row": [
            {
                "assessment_id": "a1",
                "relationship": "ANOMALOUS_UNCLASSIFIED",
                "defense_response": "NOT_COVERED",
                "composite": 0.7,
                "catch": True,
                "trust_class": "honest_anomaly",
                "trust_rank": 1,
                "discovery_value": 0.7,
                "known_benign": False,
                "false_flag": False,
                "false_flag_kind": None,
            },
            {
                "assessment_id": "a2",
                "relationship": "SAME",
                "defense_response": "COVERED",
                "composite": 0.0,
                "catch": True,
                "trust_class": "confirmed_correct",
                "trust_rank": 2,
                "discovery_value": 0.0,
                "known_benign": False,
                "false_flag": False,
                "false_flag_kind": None,
            },
        ],
    }
    findings = check_run(conformant)
    fails = [f for f in findings if f.severity == "FAIL"]
    assert not fails, f"conformant run unexpectedly failed: {fails}"


def test_scoreboard_block_sharing_zero_fields_fails():
    proxy_run = {
        "scoreboard": {
            "n_graded": 25,
            "discovery_bubbled_rate": 0.88,
        },
        "per_row": [
            {"trust_class": None, "trust_rank": None, "false_flag": None, "known_benign": None}
        ],
    }
    findings = check_run(proxy_run)
    codes = {f.code for f in findings}
    assert "scoreboard_block_is_not_the_contract" in codes


def test_per_row_dropping_trust_and_false_flag_fails():
    run_json = {
        "scoreboard": {
            "hunt_id": "h",
            "n_records": 1,
            "catch_count": 1,
            "catch_rate": 1.0,
            "trust_mean_rank": 1.0,
            "discovery_total": 0.1,
            "discovery_mean": 0.1,
            "false_flag_count": 0,
        },
        "per_row": [{"discovery_value": 0.1, "catch": True}],
    }
    findings = check_run(run_json)
    codes = {f.code for f in findings}
    assert "per_row_drops_correctness_fields" in codes


def test_seeded_violation_top_level_only_matching_misses_r6():
    """The earlier draft of this guard matched only TOP-LEVEL keys and missed
    R.6 -- the very run it was written to catch -- because R.6's scoreboard
    block and per_row correctness fields nest one level under the report
    root. Reverting to that behaviour here and asserting R.6 slips through
    proves the leaf-matching fix (`_leaf`) is load-bearing, not incidental."""
    r6_path = REPO_ROOT / "docs" / "BULLY_LOOP_MILESTONE_RUN_R6_V1.json"
    run_json = json.loads(r6_path.read_text())

    def _top_level_only_leaf(flat_top_level_only: dict, name: str):
        return flat_top_level_only.get(name)

    top_level_only = dict(run_json)  # no recursive flatten -- the seeded regression
    correctness_present = all(
        _top_level_only_leaf(top_level_only, f) is not None
        for f in ("trust_mean_rank", "false_flag_count")
    )
    assert not correctness_present, (
        "seeded check: top-level-only matching must NOT find the correctness axis "
        "in R.6 (it is nested), proving the real guard's leaf-matching is necessary"
    )


def test_check_run_signature_has_no_new_scoring_path():
    """W4: this module adds a conformance GUARD, not a scorer -- confirm
    `scoreboard.py` exposes no new public scoring entry point beyond its
    original three, and that this module never imports a parallel scorer."""
    assert set(scoreboard_mod.__all__) == {"score_record", "update", "report"}
    src = inspect.getsource(
        __import__(
            "portal.modules.security.core.bully.scoreboard_conformance",
            fromlist=["check_run"],
        )
    )
    assert "def score(" not in src
    assert "def score_record(" not in src
