"""Screen and confirm tiers: `tier` records how a row was created and never
decides membership in a comparison (spec: docs/WFE_ROOT_CAUSES_20261013.md)."""

from __future__ import annotations

import json

import pytest
import yaml

from tests.wfe import campaign as camp

SCREEN_TASKS = 10
TOTAL_TASKS = 30
WS = "auto-coding"


@pytest.fixture
def plan(tmp_path, monkeypatch):
    """A 30-task suite with the first 10 screenable, and one incumbent/candidate cell."""
    suites = tmp_path / "suites"
    suites.mkdir()
    (suites / "home.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "id": f"t{i:02d}",
                    "instruction": "Do it.",
                    "checkers": [{"type": "answer_contains", "patterns": ["TASK COMPLETE"]}],
                    **({"screen": True} if i < SCREEN_TASKS else {}),
                }
            )
            + "\n"
            for i in range(TOTAL_TASKS)
        )
    )
    monkeypatch.setattr(camp, "SUITE_DIR", suites)
    p = tmp_path / "plan.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "workloads": {
                    WS: {
                        "home": "home",
                        "discovery": [],
                        "arms": {"incumbent": "m1", "challengers": ["m2"]},
                    }
                }
            }
        )
    )
    return p


def _tasks(rows, arm=None):
    return {
        (r["suite"], r["task_id"])
        for r in rows
        if r["workspace"] == WS and (arm is None or r["arm"] == arm)
    }


class TestTierExpansion:
    def test_screen_takes_repeat_zero_of_the_screen_tasks(self, plan):
        rows = camp.expand_matrix(plan, 3, tier="screen")
        assert {r["tier"] for r in rows} == {"screen"}
        assert {r["repeat"] for r in rows} == {0}
        assert len(_tasks(rows, "m2")) == SCREEN_TASKS
        assert len(rows) == 2 * SCREEN_TASKS

    def test_confirm_takes_every_task_at_every_repeat(self, plan):
        rows = camp.expand_matrix(plan, 3, tier="confirm")
        assert {r["tier"] for r in rows} == {"confirm"}
        assert {r["repeat"] for r in rows} == {0, 1, 2}
        assert len(_tasks(rows, "m2")) == TOTAL_TASKS
        assert len(rows) == 2 * TOTAL_TASKS * 3

    def test_run_id_is_unchanged_by_tier(self, plan):
        """The stored identity of a row must not move when tiers arrive, or an
        in-flight campaign's recorded rows stop matching its matrix."""
        screen = camp.expand_matrix(plan, 3, tier="screen")
        confirm = camp.expand_matrix(plan, 3, tier="confirm")
        assert {r["run_id"] for r in screen} <= {r["run_id"] for r in confirm}
        assert all(r["run_id"].endswith("|r0") for r in screen)


class TestConfirmAppendReusesScreenRows:
    def _campaign_rows(self, plan):
        """What the campaign holds after a screen, then a confirm append."""
        screen = camp.expand_matrix(plan, 3, tier="screen")
        confirm = camp.expand_matrix(plan, 3, tier="confirm")
        known = {r["run_id"] for r in screen}
        added = [r for r in confirm if r["run_id"] not in known]
        return screen, added, screen + added

    def test_the_append_duplicates_nothing_and_reruns_nothing(self, plan):
        screen, added, _ = self._campaign_rows(plan)
        assert not ({r["run_id"] for r in screen} & {r["run_id"] for r in added})
        assert len(screen) == len({r["run_id"] for r in screen})

    def test_a_ten_task_screen_then_a_confirm_compares_thirty_not_twenty(self, plan):
        """`tier` records only how a row was created: a confirm comparison takes
        every row of the cell, so the screen rows reused as repeat 0 count.

        Filtering the cell by `tier == "confirm"` would leave the ten screenable
        tasks holding repeats 1 and 2 but not 0 — an incomplete repeat set, which
        the decision rule excludes — so the comparison would fall to twenty."""
        _, _, rows = self._campaign_rows(plan)
        cell = [r for r in rows if r["workspace"] == WS and r["arm"] == "m2"]
        assert len(_tasks(cell)) == TOTAL_TASKS

        seen: dict[tuple[str, str], set] = {}
        for r in cell:
            if r["tier"] == "confirm":
                seen.setdefault((r["suite"], r["task_id"]), set()).add(r["repeat"])
        comparable = {k for k, reps in seen.items() if reps == {0, 1, 2}}
        assert len(comparable) == TOTAL_TASKS - SCREEN_TASKS

    def test_the_reused_screen_row_is_repeat_zero_of_the_confirm(self, plan):
        screen, _, rows = self._campaign_rows(plan)
        reused = [
            r for r in rows if r["tier"] == "screen" and r["workspace"] == WS and r["arm"] == "m2"
        ]
        assert {r["repeat"] for r in reused} == {0}
        assert len(reused) == SCREEN_TASKS
        assert {r["run_id"] for r in reused} <= {r["run_id"] for r in screen}


def test_pending_confirm_rows_put_unseen_tasks_first_and_finish_rep_zero_first(plan):
    rows = camp.expand_matrix(plan, 3, only_arm="m2", tier="confirm")
    reused = next(r for r in rows if r["task_id"] == "t00" and r["repeat"] == 0)
    reused.update(state="PASS", reused_from="screen/original-run")
    pending = [r for r in rows if r["run_id"] != reused["run_id"]]

    ordered = camp._order_pending_rows(pending, {"rows": rows})
    repeat_zero = [r for r in ordered if r["repeat"] == 0]
    repeat_one = [r for r in ordered if r["repeat"] == 1]

    assert repeat_zero and repeat_one
    assert ordered.index(repeat_zero[-1]) < ordered.index(repeat_one[0])
    assert repeat_zero[0]["task_id"] == "t01"
    assert all(r["task_id"] != "t00" for r in repeat_zero)
    assert repeat_one[-1]["task_id"] == "t00"


class TestAdvance:
    def test_advance_keeps_the_listed_candidates(self, plan, tmp_path):
        adv = tmp_path / "advance.yaml"
        adv.write_text(yaml.safe_dump({WS: ["m2"]}))
        rows = camp.expand_matrix(plan, 1, tier="confirm", advance=camp.load_advance(adv))
        assert {r["arm"] for r in rows} == {"m1", "m2"}

    def test_advance_never_drops_the_incumbent(self, plan, tmp_path):
        """A candidate dropped at the screen still needs its baseline expanded;
        without the incumbent the cell cannot be compared at all."""
        adv = tmp_path / "advance.yaml"
        adv.write_text(yaml.safe_dump({WS: []}))
        rows = camp.expand_matrix(plan, 1, tier="confirm", advance=camp.load_advance(adv))
        assert {r["arm"] for r in rows} == {"m1"}

    def test_no_advance_file_expands_every_arm(self, plan):
        rows = camp.expand_matrix(plan, 1, tier="confirm", advance=camp.load_advance(None))
        assert {r["arm"] for r in rows} == {"m1", "m2"}
