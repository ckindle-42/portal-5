"""The general family's production suites: sound under the controls gate, gold reproduced
independently, every deciding fact declared, no gold stated, and the attainability check able to
fail; the decision plan's arms are checked against portal.yaml, backends.yaml and tool_modes.yaml."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_general_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITES = REPO / "tests/wfe/suites"
PLAN = REPO / "tests/wfe/plans/general_decision_v1.yaml"
FULL = {
    t["id"]: t
    for t in map(json.loads, (SUITES / "general_production.jsonl").read_text().splitlines())
}
CORE = {
    t["id"]: t
    for t in map(json.loads, (SUITES / "general_core_production.jsonl").read_text().splitlines())
}


def _kind(kind: str, suite: dict | None = None) -> list[dict]:
    return [t for t in (suite or FULL).values() if t["kind"] == kind]


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def test_the_suites_are_sound_balanced_and_the_core_is_the_computed_and_memory_half():
    assert len(FULL) == 48 and sum(t["screen"] for t in FULL.values()) == 16
    for kind, n in gen.COUNTS.items():
        assert len(_kind(kind)) == n, kind
        assert sum(t["screen"] for t in _kind(kind)) == gen.SCREEN[kind], kind
    assert len(CORE) == 36 and sum(t["screen"] for t in CORE.values()) == 12
    assert set(CORE) == {i for i, t in FULL.items() if t["kind"] in ("python", "notool", "memory")}
    for name in ("general_production", "general_core_production"):
        path = SUITES / f"{name}.jsonl"
        assert controls.check_suite(path) == []
        assert all(
            controls.schema_failures(t) == []
            for t in map(json.loads, path.read_text().splitlines())
        )


def test_lanes_mark_the_computed_and_memory_halves():
    lanes = {t["lane"] for t in FULL.values()}
    assert lanes == {"computed", "memory", "knowledge", "document"}
    assert all(t["lane"] == "computed" for t in _kind("python") + _kind("notool"))


def test_every_task_but_no_tools_and_injected_memory_is_graded_on_answer_and_trace():
    for t in FULL.values():
        kinds = [c["type"] for c in t["checkers"]]
        if t["kind"] == "notool":
            assert t.get("no_tools") and "tool_grounded" not in kinds
        elif t["kind"] == "memory" and int(t["id"][-2:]) in gen.INJECTED:
            assert "tool_grounded" not in kinds  # grounding rule pending the live read
        else:
            assert "tool_grounded" in kinds, t["id"]
    assert {t["id"] for t in _kind("memory") if "tool_grounded" not in str(t["checkers"])} == {
        f"gen-memory-{n:02d}" for n in gen.INJECTED
    }


def test_the_controls_pass_with_a_trace_and_fail_without_it_or_with_a_wrong_answer():
    def run(task, answer, calls):
        return apply_checkers(
            task, CheckContext(task=task, final_text=answer, tool_calls=calls)
        ).outcome

    for t in FULL.values():
        if t["kind"] == "document":
            continue  # file controls are run by controls.check_suite (sound-suite test)
        good, calls = t["controls"]["pass"][0]["answer"], t["controls"]["pass"][0]["tool_calls"]
        assert run(t, good, calls) == Outcome.PASS, t["id"]
        assert run(t, t["controls"]["fail"][-1]["answer"], calls) == Outcome.FAIL, t["id"]
        if any(c["type"] == "tool_grounded" for c in t["checkers"]):
            assert run(t, good, []) == Outcome.FAIL, t["id"]


def test_the_instruction_never_states_the_gold():
    for t in FULL.values():
        if t["kind"] == "document":
            continue  # asserted by the documents slice
        if t["id"] == "gen-notool-02":
            continue  # a selection: the answer is one of the names the premises introduce
        body = t["instruction"].replace(gen.FORMAT, "")
        assert not re.search(gen._pattern(_gold(t)), body), t["id"]


@pytest.mark.parametrize("n", range(gen.COUNTS["python"]))
def test_the_reference_code_prints_the_gold(n):
    task = FULL[f"gen-python-{n:02d}"]
    code = task["controls"]["pass"][0]["tool_calls"][0]["args"]["code"]
    out = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert out.stdout.strip() == _gold(task), (out.stdout, out.stderr[:200])


def test_python_golds_agree_with_a_second_derivation():
    body, _, gold = gen.python_case(2)
    a, b = (int(x) for x in re.findall(r"divisible by (\d+) or by (\d+)", body)[0])
    top = int(re.search(r"to (\d+) are", body).group(1))
    both = top // (a * b // __import__("math").gcd(a, b))
    either = top // a + top // b - 2 * both
    assert str(either) == gold


def test_notool_golds_agree_with_a_second_derivation():
    q, gold = gen.notool_case(0)
    start, k = re.search(r"Today is (\w+)", q).group(1), int(re.search(r"(\d+) days", q).group(1))
    assert gen._DAYS[(gen._DAYS.index(start) + k) % 7] == gold
    q, gold = gen.notool_case(1)
    inflow, outflow, cap = (int(x) for x in re.findall(r"(\d+) litres", q))
    assert cap / (inflow - outflow) == int(gold)
    q, gold = gen.notool_case(3)
    h, m = (int(x) for x in re.search(r"(\d\d):(\d\d)", q).groups())
    add = int(re.search(r"(\d+) minutes later", q).group(1))
    assert f"{(h * 60 + m + add) // 60 % 24:02d}:{(h * 60 + m + add) % 60:02d}" == gold
    q, gold = gen.notool_case(6)
    vehicles, crossings, days = (int(x) for x in re.findall(r"(\d+)", q))
    assert vehicles * crossings * days == int(gold)
    q, gold = gen.notool_case(7)
    deposit = int(re.search(r"deposit of (\d+) credits", q).group(1))
    rate, years = (
        int(x) for x in re.findall(r"(\d+) percent", q)[:1] + re.findall(r"over (\d+) years", q)
    )
    assert deposit * rate * years // 100 == int(gold)
    q, gold = gen.notool_case(8)
    t1, t2 = re.findall(r"(\d\d):(\d\d)", q)
    mins = (int(t2[0]) * 60 + int(t2[1])) - (int(t1[0]) * 60 + int(t1[1]))
    assert mins == int(gold)
    q, gold = gen.notool_case(9)
    serves = int(re.search(r"recipe for (\d+) people", q).group(1))
    grams = int(re.search(r"uses (\d+) grams", q).group(1))
    want = int(re.search(r"for (\d+) people\?", q).group(1))
    assert grams * want // serves == int(gold)


def test_the_core_golds_are_unique():
    golds = [_gold(t) for t in CORE.values()]
    assert len(golds) == len(set(golds))


def test_memory_and_kb_stores_hold_the_gold_and_a_third_are_imperative():
    for t in _kind("memory") + _kind("kb"):
        stores = " ".join(list(t.get("kb_seed", {}).values()) + t.get("memory_seed", []))
        assert _gold(t) in stores, t["id"]
    for kind in ("memory", "kb"):
        starts = [t["instruction"].split()[0] for t in _kind(kind)]
        assert sum(w in ("Look", "Check", "Find") for w in starts) * 3 >= len(starts) - 1, kind
    assert all("kb_seed" not in t for t in _kind("memory"))


def test_the_document_tasks_are_the_documents_suites_with_their_checkers():
    docs = {
        t["id"]: t
        for t in map(json.loads, (SUITES / "documents_production.jsonl").read_text().splitlines())
    }
    for n, source in enumerate(gen.DOC_SOURCE):
        mine, theirs = FULL[f"gen-document-{n:02d}"], docs[source]
        for key in ("instruction", "checkers", "controls", "requires_tools"):
            assert mine[key] == theirs[key], (source, key)
        assert mine.get("seed_b64") == theirs.get("seed_b64")


def test_deciding_facts_are_declared_for_every_task_that_reaches_a_tool():
    gen.build()
    reads = [t for t in _kind("document") if t["id"] not in gen.REFERENCE_CALLS]
    for t in FULL.values():
        if t["kind"] not in ("notool", "document") or t in reads:
            assert gen.DECIDING_FACTS[t["id"]], t["id"]
    assert all(
        t["id"] in gen.REFERENCE_CALLS
        for t in _kind("document")
        if "create" in t["instruction"].lower()[:8]
    )


def test_the_suites_regenerate_identically():
    for mod in ("docx", "openpyxl", "pptx"):
        pytest.importorskip(mod)
    built = gen.build()
    assert (
        "".join(json.dumps(t) + "\n" for t in built)
        == (SUITES / "general_production.jsonl").read_text()
    )
    assert (
        "".join(json.dumps(t) + "\n" for t in gen.build_core(built))
        == (SUITES / "general_core_production.jsonl").read_text()
    )


def test_attainability_fails_when_a_fact_is_not_exposed(monkeypatch):
    from tests.wfe import eval_mode
    from tests.wfe.e2e import general_attainability as att

    monkeypatch.setattr(eval_mode, "eval_post", lambda *_: None)

    gen.build()

    def silent(tool, args, scope):
        return json.dumps({"success": True, "stdout": "", "results": [], "memories": []})

    for tid in ("gen-python-00", "gen-memory-00", "gen-kb-00"):
        assert any("fact not exposed" in f for f in att.check_task(FULL[tid], silent)), tid
    assert att.check_task(FULL["gen-notool-00"], silent) == []


def test_the_plan_arms_are_served_fit_the_window_and_the_suite_tools_are_allowed():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    assert set(plan) == {
        "general-fast",
        "general-deep",
        "auto-daily",
        "auto-general-uncensored",
        "auto-uncensored-throwaway",
    }
    for ws, wl in plan.items():
        groups = set(backends["workspace_routing"][ws])
        served = {
            m["id"]
            for b in backends["backends"]
            if b["group"] in groups
            for m in b.get("models") or []
        }
        arms = wl["arms"]
        assert portal[ws]["model_hint"] in [arms["incumbent"], *arms["challengers"]], ws
        assert wl["tool_mode"] == "production", ws
        assert 2 <= len(arms["challengers"]) <= 3, ws
        for tag in [arms["incumbent"], *arms["challengers"]]:
            assert tag in served, (ws, tag)
            window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
            assert window >= portal[ws]["context_limit"], (ws, tag)
        suite = FULL if wl["home"] == "general_production" else CORE
        needed = {tool for t in suite.values() for tool in t["requires_tools"]}
        assert needed <= set(modes[ws]["allow"]), (ws, sorted(needed - set(modes[ws]["allow"])))
