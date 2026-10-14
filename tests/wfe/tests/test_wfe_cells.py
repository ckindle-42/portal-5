"""A cell's expected task set comes from the matrix, and its baseline from this
campaign (spec: docs/WFE_ROOT_CAUSES_20261013.md)."""

from __future__ import annotations

import pytest

from tests.wfe import report as rep

WS = "auto-compliance"


def _row(arm, task, suite="home", tier="confirm", repeat=0, role="challenger"):
    return {
        "run_id": f"{WS}|{arm}|{suite}|{task}|r{repeat}",
        "workspace": WS,
        "arm": arm,
        "model": arm,
        "arm_role": role,
        "suite": suite,
        "task_id": task,
        "repeat": repeat,
        "tier": tier,
        "state": "PENDING",
    }


def _manifest(rows):
    return {"campaign_id": "c", "rows": rows}


class TestExpectedSets:
    def test_the_expected_set_comes_from_the_matrix_not_the_rows(self):
        """A task missing from BOTH arms still has to count against the excluded
        budget, or a half-finished campaign reads as a complete one."""
        manifest = _manifest(
            [
                _row("inc", "t1", role="incumbent"),
                _row("inc", "t2", role="incumbent"),
                _row("cand", "t1"),
                _row("cand", "t2"),
            ]
        )
        sets = rep.expected_sets(manifest, WS)
        assert sets["inc"] == {("home", "t1"), ("home", "t2")}
        assert sets["cand"] == {("home", "t1"), ("home", "t2")}
        # Only one arm actually ran anything; the set is unchanged.
        thin = _manifest([_row("inc", "t1", role="incumbent"), _row("cand", "t1")])
        assert rep.expected_sets(thin, WS)["cand"] == {("home", "t1")}

    def test_matching_arms_compare_over_their_shared_set(self):
        manifest = _manifest(
            [
                _row("inc", "t1", role="incumbent"),
                _row("inc", "t2", role="incumbent"),
                _row("cand", "t1"),
                _row("cand", "t2"),
            ]
        )
        assert rep.cell_expected(manifest, WS, "inc", "cand") == {("home", "t1"), ("home", "t2")}

    def test_arms_that_expect_different_tasks_error_rather_than_compare(self):
        manifest = _manifest(
            [
                _row("inc", "t1", role="incumbent"),
                _row("inc", "t2", role="incumbent"),
                _row("cand", "t1"),
            ]
        )
        with pytest.raises(SystemExit, match="do not expect the same tasks"):
            rep.cell_expected(manifest, WS, "inc", "cand")

    def test_other_workspaces_do_not_leak_into_the_set(self):
        manifest = _manifest(
            [
                _row("inc", "t1", role="incumbent"),
                _row("cand", "t1"),
                {**_row("inc", "t9", role="incumbent"), "workspace": "auto-coding"},
            ]
        )
        assert rep.expected_sets(manifest, WS)["inc"] == {("home", "t1")}

    def test_the_screen_set_is_the_rows_a_screen_created(self):
        manifest = _manifest(
            [
                _row("inc", "t1", tier="screen", role="incumbent"),
                _row("inc", "t2", tier="confirm", role="incumbent"),
                _row("cand", "t1", tier="screen"),
                _row("cand", "t2", tier="confirm"),
            ]
        )
        assert rep.screen_expected(manifest, WS, "inc") == {("home", "t1")}
        assert rep.screen_expected(manifest, WS, "cand") == {("home", "t1")}
