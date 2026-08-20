"""W.3 -- the run publishes the contract, not a proxy
(TASK_BULLY_SCOREBOARD_CONFORMANCE_V1).

Seeded proof that `bully_loop_milestone_run.py`'s published `"scoreboard"`
block is the LITERAL `scoreboard.update()` return (minus the bulky
per-record `records` list, carried separately as `per_row`) -- never a proxy
ratio, and that `discovery_bubbled_rate` is gone from the module entirely."""

from __future__ import annotations

import ast
from pathlib import Path

from portal.modules.security.core.bully import scoreboard as scoreboard_mod

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_SCRIPT = REPO_ROOT / "scripts" / "bully_loop_milestone_run.py"


def test_discovery_bubbled_rate_deleted_from_codebase():
    src = RUN_SCRIPT.read_text()
    assert "discovery_bubbled_rate" not in src


def test_run_script_scoreboard_block_is_literal_update_return():
    """The published `"scoreboard"` dict is built from `scoreboard_result`
    (the real `scoreboard.update()` return), not hand-assembled counts."""
    src = RUN_SCRIPT.read_text()
    assert "scoreboard_result = scoreboard_mod.update(hunt_id, scoreboard_records)" in src
    assert '"scoreboard": {k: v for k, v in scoreboard_result.items() if k != "records"}' in src


def test_grade_distribution_is_a_separate_key_from_scoreboard():
    """Relationship counts / pyramid distribution may still be published,
    but never under the "scoreboard" name (they are not scoreboard.update()
    fields) -- they live under a distinct "grade_distribution" key."""
    src = RUN_SCRIPT.read_text()
    assert '"grade_distribution": {' in src
    tree = ast.parse(src)
    report_dict_keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "scoreboard" in keys and "grade_distribution" in keys and "per_row" in keys:
                report_dict_keys = set(keys)
    assert "scoreboard" in report_dict_keys
    assert "grade_distribution" in report_dict_keys
    assert "n_anomalous_unclassified" not in report_dict_keys  # nested, not top-level


def test_published_scoreboard_keys_equal_update_contract_exactly():
    """The seeded contract test: build the same shape the run script
    publishes (update()'s return minus `records`) and assert its keys equal
    scoreboard.update()'s keys exactly -- no extra proxy fields, nothing
    missing."""
    result = scoreboard_mod.update("hunt-w3", [])
    published = {k: v for k, v in result.items() if k != "records"}
    assert set(published.keys()) == set(result.keys()) - {"records"}
    # And re-derive the same call the run script makes, to prove no field is
    # silently dropped or renamed between update() and the published block.
    expected_fields = {
        "hunt_id",
        "n_records",
        "catch_count",
        "catch_rate",
        "trust_mean_rank",
        "discovery_total",
        "discovery_mean",
        "false_flag_count",
    }
    assert set(published.keys()) == expected_fields
