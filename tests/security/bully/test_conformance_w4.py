"""W.4 -- the run self-checks conformance before publishing
(TASK_BULLY_SCOREBOARD_CONFORMANCE_V1).

A run may not publish a headline it would itself reject. Verifies the
refusal wiring in `bully_loop_milestone_run.py` (self-check computed before
`_publish`, non-zero exit and no publish on FAIL) and exercises the
underlying `conformance_report` contract the wiring depends on."""

from __future__ import annotations

from pathlib import Path

from portal.modules.security.core.bully.scoreboard_conformance import conformance_report

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_SCRIPT = REPO_ROOT / "scripts" / "bully_loop_milestone_run.py"


def test_run_script_computes_self_check_before_publish():
    src = RUN_SCRIPT.read_text()
    self_check_idx = src.index("self_check = conformance_mod.conformance_report(report)")
    refuse_idx = src.index('if self_check["verdict"] == "FAIL":', self_check_idx)
    # the terminal (post-loop) _publish call, not the earlier BLOCKED-path ones
    publish_idx = src.index("_publish(report, args.out_dir)", refuse_idx)
    assert self_check_idx < refuse_idx < publish_idx, (
        "self-check must be computed and checked BEFORE the terminal _publish call"
    )


def test_run_script_refuses_on_fail_before_publish_call():
    """The refusal branch must `return` before reaching the _publish call
    that follows it -- i.e. there must be a `return` between the FAIL check
    and the second (post-check) _publish call."""
    src = RUN_SCRIPT.read_text()
    refuse_block_start = src.index('if self_check["verdict"] == "FAIL":')
    next_publish = src.index("_publish(report, args.out_dir)", refuse_block_start)
    block = src[refuse_block_start:next_publish]
    assert "return 1" in block


def test_conformance_report_on_a_proxy_run_is_fail():
    """A run assembled the OLD way (proxy 'scoreboard' block, no
    correctness axis) must self-check to FAIL -- proving the wiring would
    actually catch the R.6-shaped mistake if repeated."""
    proxy_run = {
        "scoreboard": {"n_graded": 10, "discovery_bubbled_rate": 0.5},
        "per_row": [{"discovery_value": 0.5, "catch": True}],
    }
    result = conformance_report(proxy_run)
    assert result["verdict"] == "FAIL"


def test_conformance_report_on_a_conformant_run_is_pass():
    conformant_run = {
        "scoreboard": {
            "hunt_id": "h",
            "n_records": 1,
            "catch_count": 1,
            "catch_rate": 1.0,
            "trust_mean_rank": 2.0,
            "discovery_total": 0.0,
            "discovery_mean": None,
            "false_flag_count": 0,
        },
        "per_row": [
            {
                "assessment_id": "a1",
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
            }
        ],
    }
    result = conformance_report(conformant_run)
    assert result["verdict"] == "PASS"
