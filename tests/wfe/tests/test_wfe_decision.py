"""Cause C4: the decision rule, pinned case by case."""

from __future__ import annotations

import pytest

from tests.wfe import decision as dc

S = "suite"


def rows(spec: dict[str, str], suite: str = S) -> list[dict]:
    code = {"P": "PASS", "F": "FAIL", "B": "BLOCKED", "H": "HARNESS_ERROR"}
    return [
        {"suite": suite, "task_id": t, "repeat": i, "outcome": code[c]}
        for t, outs in spec.items()
        for i, c in enumerate(outs)
    ]


def ids(n: int, prefix: str = "t", suite: str = S) -> set:
    return {(suite, f"{prefix}{i}") for i in range(n)}


def arms(n: int, inc: str, cand: str) -> tuple[dict, dict]:
    return {f"t{i}": inc for i in range(n)}, {f"t{i}": cand for i in range(n)}


def test_repeats_are_the_stored_zero_based_indices():
    s, e = dc.task_scores(rows({"a": "PPF", "b": "FFF"}), 3)
    assert s == {(S, "a"): 2 / 3, (S, "b"): 0.0} and e == {}
    assert (
        dc.task_scores(
            [{"suite": S, "task_id": "a", "repeat": r, "outcome": "PASS"} for r in (1, 2, 3)], 3
        )[0]
        == {}
    )


def test_missing_repeat_or_ungradeable_outcome_excludes_the_task():
    s, e = dc.task_scores(rows({"a": "PP", "b": "PBP", "c": "PPP"}), 3)
    assert set(s) == {(S, "c")} and set(e) == {(S, "a"), (S, "b")}


def test_tasks_missing_from_both_arms_count_against_the_limit():
    inc, cand = arms(30, "FFF", "PPP")  # 50 expected, 30 completed: 40% missing
    c = dc.confirm(rows(inc), rows(cand), ids(50))
    assert c.verdict == dc.NO_DECISION and c.reason.startswith("excluded 20/50")


def test_task_missing_from_one_arm_is_excluded():
    inc, cand = arms(33, "FFF", "PPP")
    del cand["t0"]
    c = dc.confirm(rows(inc), rows(cand), ids(33))
    assert c.n == 32 and "candidate missing" in c.excluded[(S, "t0")] and c.verdict == dc.BETTER


def test_rows_outside_the_expected_set_are_rejected():
    inc, cand = arms(31, "FFF", "PPP")
    with pytest.raises(ValueError, match="outside the expected set"):
        dc.confirm(rows(inc), rows(cand), ids(30))


def test_same_task_id_in_two_suites_is_two_tasks():
    a = rows({"t0": "PPP"}, "s1") + rows({"t0": "FFF"}, "s2")
    s, _ = dc.task_scores(a, 3)
    assert s == {("s1", "t0"): 1.0, ("s2", "t0"): 0.0}


def test_floor_counts_compared_tasks_not_rows():
    inc, cand = arms(29, "FFF", "PPP")
    assert dc.confirm(rows(inc), rows(cand), ids(29)).verdict == dc.NO_DECISION


def test_clear_win_is_better():
    inc, cand = arms(31, "FFF", "PPP")
    c = dc.confirm(rows(inc), rows(cand), ids(31))
    assert c.verdict == dc.BETTER and c.n == 31 and c.wins == 31


def test_identical_arms_are_not_separated():
    inc, cand = arms(31, "PPF", "PPF")
    assert dc.confirm(rows(inc), rows(cand), ids(31)).verdict == dc.NOT_SEPARATED


def test_repeat_level_difference_counts_as_a_task_win():
    inc, cand = arms(31, "PPF", "PPP")
    assert dc.confirm(rows(inc), rows(cand), ids(31)).verdict == dc.BETTER


def test_asymmetric_instrument_failures_over_ten_percent_block_a_decision():
    inc, cand = arms(31, "FFF", "PPP")
    for i in range(4):
        cand[f"t{i}"] = "HHH"
    c = dc.confirm(rows(inc), rows(cand), ids(31))
    assert c.verdict == dc.NO_DECISION and c.reason.startswith("excluded")


def test_31_task_suite_with_3_arguable_keeps_31_and_flips_them_worst_case():
    inc = {f"t{i}": "FFF" if i < 12 else "PPP" for i in range(31)}
    cand = {f"t{i}": "PPP" for i in range(31)}
    cand["t30"] = "FFF"
    c = dc.confirm(rows(inc), rows(cand), ids(31), arguable={(S, "t0"), (S, "t1"), (S, "t2")})
    assert c.n == 31 and c.verdict == dc.NO_DECISION and "arguable" in c.reason


def test_robust_win_survives_the_arguable_worst_case():
    inc, cand = arms(31, "FFF", "PPP")
    arg = {(S, "t0"), (S, "t1"), (S, "t2")}
    assert dc.confirm(rows(inc), rows(cand), ids(31), arguable=arg).verdict == dc.BETTER


def test_sign_test_is_exact_and_two_sided():
    assert dc.sign_test_p(0, 0) == 1.0
    assert dc.sign_test_p(5, 0) == pytest.approx(0.0625)
    assert dc.sign_test_p(6, 0) == pytest.approx(0.03125)


def test_curtail_guaranteed_better_after_worst_case_future_tasks():
    expected = ids(36)
    completed = {(S, f"t{i}") for i in range(27)}
    inc = rows(dict.fromkeys((f"t{i}" for i in range(36)), "FFF"))
    cand = rows(dict.fromkeys((f"t{i}" for i in range(27)), "PPP"))
    cell = dc.curtail(inc, cand, expected, completed)
    assert cell.verdict == dc.BETTER
    assert cell.n == 27 and cell.wins == 27
    assert "worst-case p=" in cell.reason


def test_curtail_guaranteed_not_separated_when_no_remaining_sign_can_cross_alpha():
    expected = ids(36)
    completed = {(S, f"t{i}") for i in range(33)}
    inc = rows(dict.fromkeys((f"t{i}" for i in range(36)), "PPP"))
    cand_spec = {f"t{i}": ("FFF" if i == 0 else "PPP") for i in range(33)}
    cell = dc.curtail(inc, rows(cand_spec), expected, completed)
    assert cell.verdict == dc.NOT_SEPARATED
    assert cell.losses == 1


def test_curtail_waits_when_a_remaining_task_can_change_the_verdict():
    expected = ids(36)
    completed = {(S, f"t{i}") for i in range(35)}
    inc_spec = {f"t{i}": "FFF" for i in range(35)}
    inc_spec["t35"] = "PPP"
    cand_spec = {f"t{i}": ("PPP" if i < 6 else "FFF") for i in range(35)}
    assert dc.curtail(rows(inc_spec), rows(cand_spec), expected, completed) is None


def test_curtail_stops_when_the_decision_floor_cannot_be_met():
    expected = ids(12)
    inc = rows(dict.fromkeys((f"t{i}" for i in range(12)), "FFF"))
    cell = dc.curtail(inc, [], expected, set())
    assert cell.verdict == dc.NO_DECISION
    assert "at most 12" in cell.reason


def test_screen_uses_repeat_zero_and_drops_only_on_a_clear_margin():
    tasks = {f"s{i}" for i in range(10)}
    exp = {(S, t) for t in tasks}
    inc = rows(dict.fromkeys(tasks, "P"))
    lose3 = rows({t: ("F" if t in {"s0", "s1", "s2"} else "P") for t in tasks})
    lose2 = rows({t: ("F" if t in {"s0", "s1"} else "P") for t in tasks})
    assert dc.screen(inc, lose3, exp).verdict == dc.DROP
    assert dc.screen(inc, lose2, exp).verdict == dc.ADVANCE
    assert dc.screen(inc, rows({"s0": "F"}), exp).verdict == dc.ADVANCE  # too few compared


def test_real_matrix_rows_are_scored(tmp_path, monkeypatch):
    """Rows from the real expand_matrix (stored format, zero-based repeats) feed confirm()."""
    from tests.wfe import campaign

    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "workloads:\n  auto-compliance:\n    home: compliance_agentic_full\n    discovery: []\n"
        "    arms:\n      incumbent: hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k\n"
        "      challengers: [granite4.1:30b-ctx64k]\n"
    )
    matrix = campaign.expand_matrix(plan, 3)
    assert {r["repeat"] for r in matrix} == {0, 1, 2}
    by_arm: dict[str, list] = {}
    for r in matrix:
        by_arm.setdefault(r["arm_role"], []).append({**r, "outcome": "PASS"})
    expected = {dc.key(r) for r in matrix}
    c = dc.confirm(by_arm["incumbent"], by_arm["challenger"], expected)
    assert c.n == len(expected) and c.verdict == dc.NOT_SEPARATED


BASE = {
    "family_vettable": True,
    "in_catalog": True,
    "available": True,
    "family_has_suite": True,
    "needs_tools": True,
    "supports_tools": True,
    "tools_verified": True,
    "model_ctx": 65536,
    "ctx_verified": True,
    "workspace_ctx": 32768,
    "memory_fits": True,
}


@pytest.mark.parametrize(
    "change,state",
    [
        ({}, dc.ELIGIBLE),
        ({"family_vettable": False}, dc.NOT_VETTABLE),
        ({"family_vettable": False, "has_capability": False}, dc.INELIGIBLE),
        ({"in_catalog": False}, dc.MISSING),
        ({"available": False}, dc.MISSING),
        ({"family_has_suite": False}, dc.MISSING),
        ({"supports_tools": False}, dc.INELIGIBLE),
        ({"supports_tools": None, "tools_verified": False}, dc.MISSING),
        ({"supports_tools": False, "tools_verified": False}, dc.MISSING),
        ({"model_ctx": 8192}, dc.INELIGIBLE),
        ({"model_ctx": 8192, "ctx_verified": False}, dc.MISSING),
        ({"model_ctx": None}, dc.MISSING),
        ({"memory_fits": None}, dc.MISSING),
        ({"memory_fits": False}, dc.INELIGIBLE),
        ({"needs_tools": False, "supports_tools": None, "tools_verified": False}, dc.ELIGIBLE),
    ],
)
def test_eligibility_table(change, state):
    assert dc.eligibility({**BASE, **change})[0] == state


@pytest.mark.parametrize(
    "cells,intended,kw,want",
    [
        ({"a": dc.BETTER, "b": dc.WORSE}, {"a"}, {}, "FOLD"),
        ({"a": dc.BETTER, "b": dc.BETTER}, {"a"}, {}, "FOLD"),
        ({"a": dc.WORSE, "b": dc.BETTER}, {"a"}, {}, "PURPOSE"),
        ({"a": dc.DROP, "b": dc.BETTER}, {"a"}, {}, dc.NO_DECISION),
        ({"a": dc.NOT_SEPARATED, "b": dc.WORSE}, {"a"}, {}, "REDUNDANT"),
        ({"a": dc.NOT_SEPARATED}, {"a"}, {"lineage_unique": True}, "RETAIN_DIVERSITY"),
        ({"a": dc.WORSE, "b": dc.DROP}, {"a"}, {}, "REMOVE"),
        ({"a": dc.WORSE, "b": dc.DROP, "c": dc.INELIGIBLE}, {"a"}, {}, "REMOVE"),
        ({"a": dc.WORSE, "b": dc.MISSING}, {"a"}, {}, dc.NO_DECISION),
        ({"a": dc.WORSE, "b": dc.ADVANCE}, {"a"}, {}, dc.NO_DECISION),
        ({"a": dc.WORSE, "b": dc.NO_DECISION}, {"a"}, {}, dc.NO_DECISION),
        ({"a": dc.WORSE, "v": dc.NOT_VETTABLE}, {"a"}, {}, dc.NO_DECISION),
        ({"a": dc.INELIGIBLE, "b": dc.BETTER}, {"a"}, {}, dc.NO_DECISION),
        ({"b": dc.BETTER}, {"a"}, {}, dc.NO_DECISION),
        ({"a": dc.WORSE}, set(), {}, dc.NO_DECISION),
    ],
)
def test_disposition_precedence(cells, intended, kw, want):
    assert dc.dispose(cells, intended, **kw)[0] == want


def test_all_not_separated_is_never_a_removal():
    cells = dict.fromkeys(("a", "b", "c"), dc.NOT_SEPARATED)
    assert dc.dispose(cells, {"a"})[0] != "REMOVE"
