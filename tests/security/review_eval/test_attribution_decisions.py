"""The truth ledger and the pre-registered decision protocol."""

from __future__ import annotations

import pytest

from portal.modules.security.core.review_eval import attribution as at
from portal.modules.security.core.review_eval import decisions as dc


def trace(item: str, klass: str, last: str | None) -> at.TruthTrace:
    return at.TruthTrace(item, klass, last)


def test_the_ledger_names_the_stage_that_loses_the_most_truth() -> None:
    # the B1.1 shape: most items never become candidates; nothing downstream can fix that
    traces = [trace(f"a{i}", "cousin", "unit") for i in range(558)]
    traces += [trace(f"b{i}", "cousin", "retrieved") for i in range(276)]
    traces += [trace(f"c{i}", "cousin", "raised") for i in range(154)]
    led = at.ledger(traces)
    assert led.total == 988 and led.binding == "candidate"
    reached = {c.stage: c.reached for c in led.stages}
    assert reached == {
        "window": 988,
        "unit": 988,
        "candidate": 430,
        "retrieved": 430,
        "read": 154,
        "raised": 154,
    }


def test_ties_go_to_the_earliest_stage_and_a_perfect_run_binds_nothing() -> None:
    tie = at.ledger([trace("a", "k", "window"), trace("b", "k", "unit")])
    assert tie.binding == "unit"  # unit and candidate each lose one item; the earlier stage binds
    perfect = at.ledger([trace("a", "k", "raised"), trace("b", "k", "raised")])
    assert perfect.binding == ""


def test_stages_that_do_not_apply_are_skipped() -> None:
    novel = [trace("n1", "novel", "read"), trace("n2", "novel", "raised")]
    led = at.ledger(novel, skip={"retrieved"})
    assert [c.stage for c in led.stages] == ["window", "unit", "candidate", "read", "raised"]
    assert led.binding == "raised"


def test_ledger_refuses_what_it_cannot_trust() -> None:
    with pytest.raises(at.AttributionError):
        at.ledger([])
    with pytest.raises(at.AttributionError):
        at.ledger([trace("a", "k", "nonsense")])
    with pytest.raises(at.AttributionError):
        at.ledger([trace("a", "k", "raised")], skip={"nonsense"})


def test_by_class_and_markdown() -> None:
    traces = [
        trace("a", "known", "raised"),
        trace("b", "cousin", "unit"),
        trace("c", "cousin", "raised"),
    ]
    led = at.by_class(traces, skip={"novel": {"retrieved"}})
    assert set(led) == {"known", "cousin"} and led["cousin"].binding == "candidate"
    table = at.render_markdown(led)
    assert table.startswith("| class | items |") and "| cousin | 2 |" in table


# ── decisions ────────────────────────────────────────────────────────────────

RECORD = """---
id: D-T2-CLASSIFIER
question: Do inferred behaviour classes find more cousins than the curated table?
stage: candidate
arms: [curated_default, inferred, none]
metric: cousin recall at the analyst workload budget (paired exact McNemar on truth items)
adopt_if: inferred beats curated_default at p < 0.05 and loses nothing at the raised stage
anti_goals:
  - tune no threshold against the headline metric
  - edit no deprecated module
status: PREREGISTERED
---
Free text rationale.
"""


def times(mapping: dict[str, float]) -> object:
    return lambda path: mapping.get(path)


def test_a_complete_preregistered_record_is_clean() -> None:
    decision = dc.parse(RECORD)
    assert decision.arms == ("curated_default", "inferred", "none")
    assert (
        dc.problems(decision, path="d.md", binding_stage="candidate", commit_time=lambda _p: None)
        == []
    )


def test_records_must_be_complete_to_parse() -> None:
    with pytest.raises(dc.DecisionInvalid):
        dc.parse("no front matter")
    with pytest.raises(dc.DecisionInvalid, match="anti_goals"):
        dc.parse(
            RECORD.replace(
                "anti_goals:\n  - tune no threshold against the headline metric\n  - edit no deprecated module\n",
                "",
            )
        )


def test_a_decision_must_target_the_binding_stage_or_say_why() -> None:
    decision = dc.parse(RECORD.replace("stage: candidate", "stage: read"))
    out = dc.problems(decision, path="d.md", binding_stage="candidate", commit_time=lambda _p: None)
    assert any("binding stage" in p for p in out)
    justified = dc.parse(
        RECORD.replace("stage: candidate", "stage: read").replace(
            "status:", "why_not_binding: reader quality is independent\nstatus:"
        )
    )
    assert (
        dc.problems(justified, path="d.md", binding_stage="candidate", commit_time=lambda _p: None)
        == []
    )


def test_preregistration_is_verified_by_commit_order() -> None:
    resolved = RECORD.replace(
        "status: PREREGISTERED", "status: ADOPTED\nreport: r.json\nresult: inferred won, p=0.01"
    )
    decision = dc.parse(resolved)
    ok = dc.problems(
        decision,
        path="d.md",
        binding_stage=None,
        commit_time=lambda p: {"d.md": 1.0, "r.json": 2.0}.get(p),
    )
    assert ok == []
    late = dc.problems(
        decision,
        path="d.md",
        binding_stage=None,
        commit_time=lambda p: {"d.md": 3.0, "r.json": 2.0}.get(p),
    )
    assert any("not committed before" in p for p in late)
    uncommitted = dc.problems(
        decision, path="d.md", binding_stage=None, commit_time=lambda _p: None
    )
    assert any("must be committed" in p for p in uncommitted)


def test_resolved_records_need_a_report_and_result_and_preregistered_ones_must_not_have_them() -> (
    None
):
    bare = dc.parse(RECORD.replace("PREREGISTERED", "REJECTED"))
    assert any(
        "names its stamped report" in p
        for p in dc.problems(bare, path="d.md", binding_stage=None, commit_time=lambda _p: None)
    )
    early = dc.parse(
        RECORD.replace("status: PREREGISTERED", "status: PREREGISTERED\nresult: peeked")
    )
    assert any(
        "no report or result yet" in p
        for p in dc.problems(early, path="d.md", binding_stage=None, commit_time=lambda _p: None)
    )
    two_arms = dc.parse(RECORD.replace("[curated_default, inferred, none]", "[only_one]"))
    assert any(
        "control" in p
        for p in dc.problems(two_arms, path="d.md", binding_stage=None, commit_time=lambda _p: None)
    )
