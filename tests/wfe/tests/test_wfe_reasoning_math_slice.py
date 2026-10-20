"""The reasoning/math production suite: sound under the controls gate, regenerates
identically, every gold recomputable from the instruction text alone (an oracle that
does not share the generator's code path), no gold stated, every deciding fact
declared and stated, and both workspaces' plans served by their backends.yaml groups
at windows that hold the reasoning chain and the hard output cap."""

from __future__ import annotations

import itertools
import json
import math
import re
from pathlib import Path

import yaml

from portal.platform.inference.config import effective_workspace
from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_reasoning_math_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/reasoning_math_production.jsonl"
PLAN = REPO / "tests/wfe/plans/reasoning_math_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"arithmetic": 12, "combinatorics": 12, "logic-grid": 12}
WORKSPACES = ("auto-reasoning", "auto-reasoning::math")
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}
IMPERATIVE = {"Work", "Count", "Determine"}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


# --------------------------------------------------------------- the oracle


def _recompute_arithmetic(ins: str) -> str:
    if "goes up" in ins:
        base, up, down = map(
            int,
            re.findall(r"costs (\d+) credits.*?up by (\d+) percent.*?down by (\d+)", ins)[0],
        )
        final = base * (100 + up) * (100 - down) / 10000
        assert final == int(final)
        return str(int(final))
    if "tank" in ins:
        vol, fast, slow = map(
            int,
            re.findall(r"holds (\d+) litres.*?adds (\d+) litres.*?removes (\d+) litres", ins)[0],
        )
        assert vol % (fast - slow) == 0
        return str(vol // (fast - slow))
    if "clock" in ins:
        hh, mm, add = map(int, re.findall(r"shows (\d+):(\d+).*?(\d+) minutes later", ins)[0])
        total = (hh * 60 + mm + add) % 1440
        return f"{total // 60:02d}:{total % 60:02d}"
    a, b, m = map(int, re.findall(r"(\d+) raised to the power (\d+) is divided by (\d+)", ins)[0])
    return str(pow(a, b, m))


def _recompute_combinatorics(ins: str) -> str:
    if "handshakes" in ins:
        (n,) = map(int, re.findall(r"gathering of (\d+) people", ins))
        return str(n * (n - 1) // 2)
    if "committee" in ins:
        n, k = map(int, re.findall(r"club with (\d+) members.*?committee of (\d+) members", ins)[0])
        return str(math.comb(n, k))
    if "entrants" in ins:
        (n,) = map(int, re.findall(r"race has (\d+) entrants", ins))
        return str(n * (n - 1) * (n - 2))
    w, d = map(int, re.findall(r"(\d+) blocks wide and (\d+) blocks deep", ins)[0])
    return str(math.comb(w + d, w))


def _parse_clues(ins: str) -> list[tuple[str, str, str]]:
    """Every clue bullet, classified: ('not', name, ordinal) | ('before', a, b) |
    ('ahead', a, b). The bullet list is the instruction's own structure, so parsing
    it whole cannot miss a clue the way a first-match search did."""
    out = []
    for bullet in re.findall(r"^- (.+?)$", ins, re.M):
        if m := re.fullmatch(r"(\w+) did not finish (first|second|third|fourth)\.", bullet):
            out.append(("not", m.group(1), m.group(2)))
        elif m := re.fullmatch(r"(\w+) finished immediately before (\w+)\.", bullet):
            out.append(("before", m.group(1), m.group(2)))
        elif m := re.fullmatch(r"(\w+) finished somewhere ahead of (\w+)\.", bullet):
            out.append(("ahead", m.group(1), m.group(2)))
        else:
            raise AssertionError(f"unparseable clue: {bullet!r}")
    return out


def _order_fits(clues: list[tuple[str, str, str]], pos: dict[str, int]) -> bool:
    for kind, a, b in clues:
        if kind == "not" and pos[a] == ORD[b]:
            return False
        if kind == "before" and pos[a] + 1 != pos[b]:
            return False
        if kind == "ahead" and pos[a] >= pos[b]:
            return False
    return True


def _recompute_logic(ins: str) -> str:
    """Brute-force all 24 finishing orders against every parsed clue; the gold is the
    asked position's runner in the UNIQUE order the clues admit."""
    roster = re.search(r"runners \u2014 ([A-Za-z, ]+?) \u2014", ins).group(1)
    names = sorted(w.strip() for w in roster.replace(" and ", ",").split(","))
    asked = ORD[re.search(r"finished (\w+)[.?]", ins).group(1)]
    clues = _parse_clues(ins)
    assert len(clues) == len(re.findall(r"^- ", ins, re.M)), "a clue bullet went unparsed"
    sols = [
        {nm: i + 1 for i, nm in enumerate(perm)}
        for perm in itertools.permutations(names)
        if _order_fits(clues, {nm: i + 1 for i, nm in enumerate(perm)})
    ]
    assert len(sols) == 1, len(sols)
    return next(nm for nm, p in sols[0].items() if p == asked)


def _recompute(task: dict) -> str:
    """The gold, recomputed from the instruction text ALONE \u2014 no generator code.
    Fails the suite if the generator's arithmetic ever drifts from its own wording
    (the tank task once held fast*mins litres while the net rate fills it)."""
    ins, kind = task["instruction"], task["kind"]
    if kind == "arithmetic":
        return _recompute_arithmetic(ins)
    if kind == "combinatorics":
        return _recompute_combinatorics(ins)
    return _recompute_logic(ins)


# --------------------------------------------------------------- suite gates


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(t["id"].startswith(f"rm-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_no_tools_and_graded_on_answer_and_reasoning():
    for t in TASKS.values():
        assert t["no_tools"] is True and t["requires_tools"] == [] and t["agentic"] is False, t[
            "id"
        ]
        kinds = [c["type"] for c in t["checkers"]]
        assert kinds == ["answer_contains", "answer_after_reasoning"], t["id"]
        assert t["checkers"][0]["patterns"] == t["checkers"][1]["patterns"], t["id"]
        assert t["lane"] == "reasoning", t["id"]


def test_the_controls_pass_and_fail_where_they_must():
    def run(task, answer):
        ctx = CheckContext(task=task, final_text=answer)
        return apply_checkers(task, ctx).outcome

    for t in TASKS.values():
        good = t["controls"]["pass"][0]["answer"]
        assert run(t, good) == Outcome.PASS, t["id"]  # right answer, no trace: none is needed
        wrong = t["controls"]["fail"][0]["answer"]
        assert run(t, wrong) == Outcome.FAIL, t["id"]
        # the family's "right, wrong place" control: the gold buried in <think>
        think_only = t["controls"]["fail"][1]["answer"]
        assert _gold(t) in think_only, t["id"]
        assert run(t, think_only) == Outcome.FAIL, t["id"]


def test_the_instruction_never_states_the_gold():
    for t in TASKS.values():
        assert gen._leaks(t) is None, t["id"]
        if re.fullmatch(r"[\d:]+", _gold(t)):
            assert _gold(t) not in t["instruction"], t["id"]


def test_every_gold_is_recomputed_from_the_instruction_alone():
    for t in TASKS.values():
        assert _recompute(t) == _gold(t), t["id"]


def test_a_third_of_each_kind_is_imperative():
    for kind in KINDS:
        starts = [t["instruction"].split()[0] for t in _kind(kind)]
        imperative = sum(w in IMPERATIVE for w in starts)
        assert imperative * 3 >= len(starts) - 1, (kind, starts)


def test_deciding_facts_are_declared_and_stated():
    gen.build()
    for t in TASKS.values():
        facts = gen.DECIDING_FACTS[t["id"]]
        assert facts, t["id"]
        for f in facts:
            assert f.tool == "" and not f.args, (
                t["id"],
                f.why,
            )  # no tools: the prompt is the source
            assert re.search(f.pattern, t["instruction"]), (t["id"], f.why)


def test_the_golds_are_unique_across_the_suite():
    golds = [_gold(t) for t in TASKS.values()]
    assert len(golds) == len(set(golds))


def test_the_suite_regenerates_identically():
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()


def test_the_chain_fits_the_window_under_the_hard_output_cap():
    """prompt (chars/4) + predict_limit <= context_limit, per seat, per task. The
    real P-4 prompt-token measure is live and backlogged."""
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    for ws in WORKSPACES:
        w = effective_workspace(portal, ws)
        limit, cap = w["context_limit"], w["predict_limit"]
        assert cap and limit, ws
        for t in TASKS.values():
            prompt = (len(w.get("owui_system_prompt") or "") + len(t["instruction"])) / 4
            assert prompt + cap <= limit, (ws, t["id"], prompt + cap)


# --------------------------------------------------------------- the plan


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    assert sorted(plan) == sorted(WORKSPACES)
    for ws in WORKSPACES:
        wl = plan[ws]
        assert wl["home"] == "reasoning_math_production" and wl["discovery"] == []
        # every task is no_tools, so the workload declares no tool mode at all
        assert "tool_mode" not in wl, ws
        groups = set(
            backends["workspace_routing"][ws.partition("::")[0]]
        )  # a variant routes as its base
        served = {
            m["id"]
            for b in backends["backends"]
            if b["group"] in groups
            for m in b.get("models") or []
        }
        arms = wl["arms"]
        assert effective_workspace(portal, ws)["model_hint"] in [
            arms["incumbent"],
            *arms["challengers"],
        ]
        assert len(arms["challengers"]) == 3
        for tag in [arms["incumbent"], *arms["challengers"]]:
            assert tag in served, (ws, tag)
            window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
            assert window >= effective_workspace(portal, ws)["context_limit"], (ws, tag, window)


# --------------------------------------------------------------- attainability


def test_attainability_flags_a_missing_given_a_stated_gold_and_gold_drift():
    from tests.wfe.e2e import reasoning_math_attainability as att

    gen.build()
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    built = {t["id"]: _gold(t) for t in TASKS.values()}
    assert all(att.check_task(t, portal, built) == [] for t in TASKS.values())

    truncated = json.loads(json.dumps(TASKS["rm-arithmetic-00"]))
    truncated["instruction"] = "What is the final price? Give the number only."
    assert any("given not stated" in f for f in att.check_task(truncated, portal, built))

    leaked = json.loads(json.dumps(TASKS["rm-arithmetic-00"]))
    gold = _gold(leaked)
    leaked["instruction"] += f' The final price is JSON {{"answer": "{gold}"}}.'
    assert any("gold not private" in f for f in att.check_task(leaked, portal, built))

    drifted = dict.fromkeys(built, built["rm-arithmetic-00"])
    assert any(
        "gold drift" in f for f in att.check_task(TASKS["rm-combinatorics-00"], portal, drifted)
    )
