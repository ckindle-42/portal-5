"""auto-research's production suite: sound under the controls gate, regenerates identically,
every deciding fact declared, no gold stated or leaked, and the attainability check able to
fail; the decision plan's arms are checked against portal.yaml and backends.yaml."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_research_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/research_production.jsonl"
PLAN = REPO / "tests/wfe/plans/research_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"lookup": 8, "multihop": 10, "memory": 6, "conflict": 6, "absent": 6}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(t["id"].startswith(f"res-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_graded_on_its_answer_and_on_its_trace():
    for t in TASKS.values():
        kinds = [c["type"] for c in t["checkers"]]
        assert kinds[0] == "answer_contains" and "tool_grounded" in kinds, t["id"]
    assert all(
        sum(c["type"] == "tool_grounded" for c in t["checkers"]) == 2 for t in _kind("multihop")
    )


def test_the_controls_pass_with_a_trace_and_fail_without_it_or_with_a_wrong_answer():
    def run(task, answer, calls):
        ctx = CheckContext(task=task, final_text=answer, tool_calls=calls)
        return apply_checkers(task, ctx).outcome

    for t in TASKS.values():
        good, calls = t["controls"]["pass"][0]["answer"], t["controls"]["pass"][0]["tool_calls"]
        assert run(t, good, calls) == Outcome.PASS, t["id"]
        assert run(t, good, []) == Outcome.FAIL, t["id"]
        wrong = t["controls"]["fail"][1]["answer"]
        assert run(t, wrong, calls) == Outcome.FAIL, t["id"]


def test_the_instruction_never_states_the_gold():
    for t in TASKS.values():
        gold = _gold(t)
        if gold != gen.NOT_FOUND:
            assert gold not in t["instruction"], t["id"]
        else:  # the defined not-found string is the only value the instruction may name
            assert f'"answer": "{gen.NOT_FOUND}"' in t["instruction"], t["id"]
            assert "answer exactly" in t["instruction"], t["id"]


def test_a_third_of_each_kind_is_imperative():
    for kind in KINDS:
        starts = [t["instruction"].split()[0] for t in _kind(kind)]
        imperative = sum(w in ("Look", "Find", "Check") for w in starts)
        assert imperative * 3 >= len(starts) - 1, (kind, starts)


def test_deciding_facts_are_declared_for_every_task():
    gen.build()
    for t in TASKS.values():
        assert gen.DECIDING_FACTS[t["id"]], t["id"]
    assert all(len(gen.DECIDING_FACTS[t["id"]]) == 2 for t in _kind("multihop"))
    assert all(f.absent for t in _kind("absent") for f in gen.DECIDING_FACTS[t["id"]])


def test_an_absent_entity_is_in_neither_store_and_its_decoys_are_forbidden():
    for t in _kind("absent"):
        gen.build()
        entity_pattern = gen.DECIDING_FACTS[t["id"]][0].pattern
        stores = list(t["kb_seed"].values()) + t["memory_seed"]
        assert not any(re.search(entity_pattern, s) for s in stores), t["id"]
        assert re.search(entity_pattern, t["instruction"]), t["id"]
        assert len(t["checkers"][0]["forbid"]) == 3
        assert t["checkers"][0]["forbid_in_tool_output"] == [gen.NOT_FOUND]
        assert not any(gen.NOT_FOUND in s for s in stores)


def test_a_conflict_task_forbids_the_older_value_and_the_newer_record_wins():
    for t in _kind("conflict"):
        gold = _gold(t)
        loser = t["controls"]["fail"][1]["answer"]
        old = json.loads(loser)["answer"]
        assert t["checkers"][0]["forbid"] == [gen._answer_pattern(old)]
        docs = t["kb_seed"]
        dated = {
            re.search(r"Effective date: (\S+)", d).group(1): d
            for d in docs.values()
            if "Effective" in d
        }
        newest = dated[max(dated)]
        assert gold in newest and old not in newest, t["id"]


def test_seeded_names_fit_the_kb_route_and_the_rows_stay_small():
    for t in TASKS.values():
        for name in t.get("kb_seed") or {}:
            assert re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", name), name
        seeded = sum(map(len, (t.get("kb_seed") or {}).values())) + sum(
            map(len, t.get("memory_seed") or [])
        )
        assert seeded < 6000, t["id"]
    assert all("memory_seed" in t and "kb_seed" not in t for t in _kind("memory"))


def test_the_gold_is_unique_across_the_suite():
    golds = [_gold(t) for t in TASKS.values() if _gold(t) != gen.NOT_FOUND]
    assert len(golds) == len(set(golds))


def test_the_suite_regenerates_identically():
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()


def test_the_seeded_stores_hold_the_gold():
    for t in TASKS.values():
        gold = _gold(t)
        if gold == gen.NOT_FOUND:
            continue
        stores = " ".join(list((t.get("kb_seed") or {}).values()) + (t.get("memory_seed") or []))
        assert gold in stores, t["id"]


def test_attainability_fails_when_a_fact_is_not_exposed_or_a_decoy_is_reachable(monkeypatch):
    from tests.wfe import eval_mode
    from tests.wfe.e2e import research_attainability as att

    monkeypatch.setattr(eval_mode, "eval_post", lambda *_: None)

    gen.build()

    def silent(tool, args, scope):
        return json.dumps({"results": []})

    assert any("fact not exposed" in f for f in att.check_task(TASKS["res-lookup-00"], silent))

    def everything(tool, args, scope):
        return json.dumps({"results": [{"text": json.dumps(args)}]})

    absent = next(t for t in _kind("absent"))
    assert any("decoy reachable" in f for f in att.check_task(absent, everything))
    assert att.check_task(absent, silent) == []


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["auto-research"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
        "auto-research"
    ]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["auto-research"])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert arms["incumbent"] == portal["model_hint"] and plan["tool_mode"] == "production"
    assert len(arms["challengers"]) == 3
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], tag
