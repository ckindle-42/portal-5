"""The tools-specialist production suite: sound under the controls gate, regenerates
identically, every derived gold recomputable from the instruction text alone, the
answer grounded on the row's own tool trace (python stdout for the computations,
the recall read-back for the store path), and the plan's arms served by the lane's
backends.yaml group at windows that hold the tight 8k seat."""

from __future__ import annotations

import json
import math
import re
from fractions import Fraction
from pathlib import Path

import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_tools_specialist_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/tools_specialist_production.jsonl"
PLAN = REPO / "tests/wfe/plans/tools_specialist_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"compute": 12, "store-recall": 12, "chain": 12}
IMPERATIVE = {"Compute", "Store"}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


# --------------------------------------------------------------- the oracle


def _recompute(task: dict) -> str | None:
    """The derived gold, recomputed from the instruction text ALONE — no generator
    code (store-recall returns None: its payload is given, storing it is the task)."""
    ins = task["instruction"]
    if task["kind"] == "store-recall":
        return None
    if "total revenue" in ins:
        pairs = re.findall(r"(\d+) units at (\d+) credits", ins)
        return str(sum(int(u) * int(p) for u, p in pairs))
    if "HH:MM:SS" in ins:
        secs = int(re.search(r"Convert (\d+) seconds", ins).group(1))
        return f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
    if "grows by" in ins:
        pop, rate = map(
            int, re.findall(r"of (\d+) people grows by (\d+) percent every year", ins)[0]
        )
        (years,) = re.findall(r"after (\d+) years", ins)
        val = float(pop * (1 + Fraction(rate, 100)) ** int(years))
        assert abs(val - math.floor(val) - 0.5) >= 0.05, task["id"]
        return str(round(val))
    if "least common multiple" in ins:
        a, b, c = map(int, re.findall(r"least common multiple of (\d+), (\d+) and (\d+)", ins)[0])
        return str(math.lcm(a, b, c))
    if re.search(r"the value of \((\d+) - (\d+)\) squared plus (\d+)", ins):
        a, b, c = map(int, re.findall(r"the value of \((\d+) - (\d+)\) squared plus (\d+)", ins)[0])
        return str((a - b) ** 2 + c)
    if "squared plus" in ins:
        a, b = map(int, re.findall(r"the value of (\d+) squared plus (\d+) squared", ins)[0])
        return str(a**2 + b**2)
    if "factorial" in ins:
        (k,) = re.findall(r"factorial of (\d+)", ins)
        return str(math.factorial(int(k)))
    if "squared plus" in ins:
        a, b, c = map(int, re.findall(r"the value of \((\d+) - (\d+)\) squared plus (\d+)", ins)[0])
        return str((a - b) ** 2 + c)
    a, b, c = map(int, re.findall(r"the value of \((\d+) \+ (\d+)\) \* (\d+)", ins)[0])
    return str((a + b) * c)


# --------------------------------------------------------------- suite gates


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(t["id"].startswith(f"ts-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_graded_on_its_answer_and_on_its_trace():
    for t in TASKS.values():
        kinds = [c["type"] for c in t["checkers"]]
        assert kinds[0] == "answer_contains" and "tool_grounded" in kinds, t["id"]
        assert set(t["requires_tools"]) <= {"execute_python", "remember", "recall"}, t["id"]
        assert t["lane"] == "tools" and t["agentic"] is True, t["id"]
    # the store path is graded on the recall read-back, not on the write's receipt
    for t in _kind("store-recall"):
        assert t["checkers"][1]["tools"] == ["recall"], t["id"]
    for t in _kind("chain"):
        assert [c["tools"] for c in t["checkers"][1:]] == [["execute_python"], ["recall"]], t["id"]


def test_the_controls_pass_with_a_trace_and_fail_without_it_or_with_a_wrong_answer():
    def run(task, answer, calls):
        ctx = CheckContext(task=task, final_text=answer, tool_calls=calls)
        return apply_checkers(task, ctx).outcome

    for t in TASKS.values():
        good, calls = t["controls"]["pass"][0]["answer"], t["controls"]["pass"][0]["tool_calls"]
        assert run(t, good, calls) == Outcome.PASS, t["id"]
        assert run(t, good, []) == Outcome.FAIL, t["id"]  # right answer, no trace
        wrong = t["controls"]["fail"][1]["answer"]
        assert run(t, wrong, calls) == Outcome.FAIL, t["id"]  # wrong answer, real trace


def test_the_trace_uses_the_source_declared_shapes_and_schema_argument_names():
    """execute_python: {success, stdout, stderr, exit_code, timed_out}
    (code_sandbox_mcp.py:533-556); remember: {id, stored, category, graph_updated}
    (graph_memory.py:420); recall: {query, memories:[...]} (graph_memory.py:423-468).
    Argument names are the manifest's: code / text / query."""
    for t in TASKS.values():
        for c in t["controls"]["pass"][0]["tool_calls"]:
            if c["name"] == "execute_python":
                assert set(c["args"]) == {"code"}, t["id"]
                assert set(json.loads(c["output"])) == {
                    "success",
                    "stdout",
                    "stderr",
                    "exit_code",
                    "timed_out",
                }, t["id"]
            if c["name"] == "remember":
                assert set(c["args"]) == {"text"}, t["id"]
                assert json.loads(c["output"])["stored"] is True, t["id"]
            if c["name"] == "recall":
                assert set(c["args"]) == {"query"}, t["id"]
                row = json.loads(c["output"])
                assert set(row) == {"query", "memories"} and row["memories"], t["id"]
                assert set(row["memories"][0]) == {
                    "id",
                    "text",
                    "category",
                    "tags",
                    "similarity",
                }, t["id"]


def test_the_instruction_never_states_a_derived_gold():
    """store-recall's payload is GIVEN (storing it is the task, triage §5); every
    derived gold (compute, chain) must be absent from its instruction."""
    for t in TASKS.values():
        gold = _gold(t)
        if t["kind"] == "store-recall":
            assert gold in t["instruction"], t["id"]  # the payload to store
        else:
            assert gold not in t["instruction"], t["id"]


def test_every_derived_gold_is_recomputed_from_the_instruction_alone():
    for t in TASKS.values():
        expected = _recompute(t)
        if expected is not None:
            assert expected == _gold(t), t["id"]


def test_the_store_recall_read_back_carries_the_payload():
    for t in _kind("store-recall"):
        token = _gold(t)
        recall = t["controls"]["pass"][0]["tool_calls"][1]
        assert recall["name"] == "recall"
        assert token in json.loads(recall["output"])["memories"][0]["text"], t["id"]


def test_a_third_of_each_kind_is_imperative():
    for kind in KINDS:
        starts = [t["instruction"].split()[0] for t in _kind(kind)]
        imperative = sum(w in IMPERATIVE for w in starts)
        assert imperative * 3 >= len(starts) - 1, (kind, starts)


def test_deciding_facts_are_declared_in_call_order():
    gen.build()
    for t in TASKS.values():
        facts = gen.DECIDING_FACTS[t["id"]]
        assert facts and all(f.pattern and f.why and f.args for f in facts), t["id"]
        # a chain runs python -> remember -> recall; a store runs remember -> recall
        if t["kind"] == "chain":
            assert [f.tool for f in facts] == ["execute_python", "remember", "recall"], t["id"]
        if t["kind"] == "store-recall":
            assert [f.tool for f in facts] == ["remember", "recall"], t["id"]


def test_the_golds_are_unique_across_the_suite():
    golds = [_gold(t) for t in TASKS.values()]
    assert len(golds) == len(set(golds))


def test_the_suite_regenerates_identically():
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()


def test_the_tool_modes_allowlist_offers_the_three_tools_only():
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    mode = modes["tools-specialist"]
    assert mode["tool_mode"] == "production"
    assert set(mode["allow"]) == {"execute_python", "remember", "recall"}
    for t in TASKS.values():
        assert set(t["requires_tools"]) <= set(mode["allow"]), t["id"]


def test_the_window_holds_the_prompt_and_the_configured_output_budget():
    """8k is the tightest window: prompt (chars/4) plus the seat's configured
    output budget (predict_limit) must stay inside it.
    The real P-4 prompt-token measure with the three schemas is live and backlogged."""
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
        "tools-specialist"
    ]
    limit, cap = portal["context_limit"], portal["predict_limit"]
    assert cap and limit
    for t in TASKS.values():
        prompt = (len(portal.get("owui_system_prompt") or "") + len(t["instruction"])) / 4
        assert prompt + cap <= limit, (t["id"], prompt + cap)


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["tools-specialist"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
        "tools-specialist"
    ]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["tools-specialist"])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    # A decided plan: the seat it produced is one of its arms (WFE_DECISION_TOOLS_SPECIALIST).
    assert portal["model_hint"] in [arms["incumbent"], *arms["challengers"]]
    assert plan["tool_mode"] == "production"
    assert plan["home"] == "tools_specialist_production" and plan["discovery"] == []
    assert 3 <= len(arms["challengers"]) <= 6
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], (tag, window)


# --------------------------------------------------------------- attainability


def _replays(tid: str):
    """A caller that answers each tool with the declared control trace's own output
    (offline stand-in for the live MCP): build/store facts precede reads in
    DECIDING_FACTS order, so a trace-following loop must satisfy them all."""

    def call(tool, args):
        for c in TASKS[tid]["controls"]["pass"][0]["tool_calls"]:
            if c["name"] == tool and c["args"] == args:
                return c["output"]
        return ""

    return call


def test_attainability_fails_when_a_fact_is_not_exposed_and_passes_on_the_trace():
    from tests.wfe.e2e import tools_specialist_attainability as att

    gen.build()

    def silent(tool, args):
        return json.dumps({"memories": []}) if tool == "recall" else json.dumps({"stored": False})

    for tid in ("ts-chain-00", "ts-store-recall-00", "ts-compute-00"):
        assert any("fact not exposed" in f for f in att.check_task(TASKS[tid], silent)), tid
        assert att.check_task(TASKS[tid], _replays(tid)) == [], tid
