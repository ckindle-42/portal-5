"""auto-cad's production suite: sound under the controls gate, regenerates identically,
every gold volume recomputable from the instruction text alone, the gold never stated,
the answer grounded twice (a validated build and the measured volume), and the plan's
arms served by auto-cad's backends.yaml groups at windows that hold the tool schemas."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_cad_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/cad_production.jsonl"
PLAN = REPO / "tests/wfe/plans/cad_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"plate-holes": 12, "extrusion": 12, "revolve": 12}
IMPERATIVE = {"Build"}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["volume_mm3"]


# --------------------------------------------------------------- the oracle


def _recompute(task: dict) -> tuple[str, str]:
    """(gold volume, holes-or-None) recomputed from the instruction text ALONE — no
    generator code. The gold is the volume truncated to the whole number."""
    ins = task["instruction"]
    if task["kind"] == "plate-holes":
        ln, wd, ht = map(
            int, re.findall(r"is (\d+) mm long, (\d+) mm wide and (\d+) mm thick", ins)[0]
        )
        n, d = map(int, re.findall(r"with (\d+) through holes of diameter (\d+) mm", ins)[0])
        vol = ln * wd * ht - n * math.pi * (d / 2) ** 2 * ht
        return str(math.floor(vol)), str(n)
    if "right triangle" in ins:
        a, b, ln = map(int, re.findall(r"legs (\d+) mm and (\d+) mm, extruded (\d+) mm", ins)[0])
        return str(math.floor(a * b / 2 * ln)), None
    if "trapezoid" in ins:
        p, q, t, ln = map(
            int,
            re.findall(
                r"parallel sides (\d+) mm and (\d+) mm and thickness (\d+) mm, extruded (\d+) mm",
                ins,
            )[0],
        )
        return str(math.floor((p + q) / 2 * t * ln)), None
    if "solid cylinder" in ins:
        rad, h = map(int, re.findall(r"radius (\d+) mm and height (\d+) mm", ins)[0])
        return str(math.floor(math.pi * rad**2 * h)), None
    rb, rt, h = map(
        int, re.findall(r"base radius (\d+) mm, top radius (\d+) mm and height (\d+) mm", ins)[0]
    )
    return str(math.floor(math.pi * h / 3 * (rb**2 + rb * rt + rt**2))), None


# --------------------------------------------------------------- suite gates


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(t["id"].startswith(f"cad-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_graded_on_answer_build_and_measurement():
    for t in TASKS.values():
        kinds = [c["type"] for c in t["checkers"]]
        assert kinds[0] == "answer_contains" and kinds.count("tool_grounded") == 2, t["id"]
        build, volume = t["checkers"][1], t["checkers"][2]
        assert build["tools"] == ["cad_build"], t["id"]
        assert volume["tools"] == ["cad_build", "cad_measure"], t["id"]
        assert t["requires_tools"] == ["cad_build", "cad_measure"], t["id"]
        assert t["lane"] == "cad" and t["agentic"] is True, t["id"]


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


def test_the_trace_shows_a_validated_build_and_the_true_measured_volume():
    for t in TASKS.values():
        build, measure = t["controls"]["pass"][0]["tool_calls"]
        assert build["name"] == "cad_build" and '"ok": true' in build["output"], t["id"]
        assert "validated" in build["output"], t["id"]
        assert measure["name"] == "cad_measure", t["id"]
        vol = json.loads(measure["output"])["measure"]["volume"]
        assert math.floor(vol) == int(_gold(t)), t["id"]
        # the arguments are named exactly as the manifest names them
        assert set(build["args"]) == {"code"}, t["id"]
        assert set(measure["args"]) == {"object_name"}, t["id"]


def test_the_volume_evidence_cannot_be_satisfied_by_a_wrong_build():
    """A plate built without its holes measures L·W·H — the evidence must not match it."""
    for t in _kind("plate-holes"):
        m = re.search(r"is (\d+) mm long, (\d+) mm wide and (\d+) mm thick", t["instruction"])
        ln, wd, ht = (int(x) for x in m.groups())
        solid = ln * wd * ht
        evidence = t["checkers"][2]["evidence"][0]
        assert not re.search(evidence, json.dumps({"measure": {"volume": float(solid)}})), t["id"]


def test_the_instruction_never_states_the_gold():
    for t in TASKS.values():
        assert _gold(t) not in t["instruction"], t["id"]


def test_every_gold_is_recomputed_from_the_instruction_alone():
    for t in TASKS.values():
        gold, holes = _recompute(t)
        assert gold == _gold(t), t["id"]
        if holes is not None:
            assert json.loads(t["controls"]["pass"][0]["answer"])["holes"] == holes, t["id"]


def test_a_third_of_each_kind_is_imperative():
    for kind in KINDS:
        starts = [t["instruction"].split()[0] for t in _kind(kind)]
        imperative = sum(w in IMPERATIVE for w in starts)
        assert imperative * 3 >= len(starts) - 1, (kind, starts)


def test_deciding_facts_are_declared_for_every_task():
    gen.build()
    for t in TASKS.values():
        facts = gen.DECIDING_FACTS[t["id"]]
        assert [f.tool for f in facts] == ["cad_build", "cad_measure"], t["id"]
        assert all(f.args and f.pattern and f.why for f in facts), t["id"]


def test_the_tool_output_shape_is_the_bridge_source_declared_shape():
    """cad_build returns ok/stage/measure/validate/next (b123d_bridge.py:353-357);
    cad_measure returns ok/measure (:369-374). The engine measure tail carries the
    volume (tests/unit/test_cad_b123d_bridge.py:98-104); find_holes is unverified and
    is used by no checker."""
    for t in TASKS.values():
        build, measure = t["controls"]["pass"][0]["tool_calls"]
        out = json.loads(build["output"])
        assert set(out) == {"ok", "stage", "delivered", "execute", "measure", "validate", "next"}, (
            t["id"]
        )
        assert set(json.loads(measure["output"])) == {"ok", "measure"}, t["id"]
        assert all(
            "cad_find_holes" not in json.dumps(c.get("evidence") or []) for c in t["checkers"]
        ), t["id"]


def test_the_golds_are_unique_across_the_suite():
    golds = [_gold(t) for t in TASKS.values()]
    assert len(golds) == len(set(golds))


def test_the_suite_regenerates_identically():
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()


def test_the_tool_modes_allowlist_offers_the_cad_surface_only():
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    mode = modes["auto-cad"]
    assert mode["tool_mode"] == "production"
    assert set(mode["allow"]) == set(gen.CAD_TOOLS)
    # nothing the checkers ground on may be missing from the allowlist
    for t in TASKS.values():
        assert set(t["requires_tools"]) <= set(mode["allow"]), t["id"]


def test_the_chain_fits_the_window_under_the_hard_output_cap():
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto-cad"]
    limit, cap = portal["context_limit"], portal["predict_limit"]
    for t in TASKS.values():
        prompt = (len(portal.get("owui_system_prompt") or "") + len(t["instruction"])) / 4
        assert prompt + cap <= limit, (t["id"], prompt + cap)


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["auto-cad"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto-cad"]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["auto-cad"])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert portal["model_hint"] in [arms["incumbent"], *arms["challengers"]]
    assert plan["tool_mode"] == "production"
    assert plan["home"] == "cad_production" and plan["discovery"] == []
    assert len(arms["challengers"]) == 3
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], (tag, window)


# --------------------------------------------------------------- attainability


def test_attainability_fails_when_a_fact_is_not_exposed():
    from tests.wfe.e2e import cad_attainability as att

    gen.build()

    def broken(tool, args):
        return json.dumps({"ok": False, "error": "engine down"})

    assert any("fact not exposed" in f for f in att.check_task(TASKS["cad-plate-holes-00"], broken))

    def declares_the_trace(tool, args):
        """The control trace's own outputs satisfy every fact: build first, then
        measure, in one session (the live caller bakes the request id in)."""
        out = next(
            c["output"]
            for c in TASKS["cad-plate-holes-00"]["controls"]["pass"][0]["tool_calls"]
            if c["name"] == tool and c["args"] == args
        )
        return out

    assert att.check_task(TASKS["cad-plate-holes-00"], declares_the_trace) == []
