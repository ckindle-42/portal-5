"""The `auto` router's single-arm characterisation suite: sound under the controls
gate, regenerates identically, every prompt proven clear-cut offline (the production
Layer 2 keyword scorer resolves it to the gold; the harmful-intent gate stays cold),
the router's own few-shot file kept out (no-leak against routing_examples.json), the
identity exemption scoped to exactly these rows, and the plan single-arm with no
challengers because the classifier model is a pipeline env, not a request parameter."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_routing_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/routing_production.jsonl"
PLAN = REPO / "tests/wfe/plans/routing_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"auto-coding": 4, "auto-compliance": 4, "auto-security": 4, "auto-spl": 4}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 16 and sum(t["screen"] for t in TASKS.values()) == 4
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(t["id"].startswith(f"route-{kind.removeprefix('auto-')}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_no_tools_and_graded_on_the_resolved_workspace():
    for t in TASKS.values():
        assert t["no_tools"] is True and t["requires_tools"] == [] and t["agentic"] is False, t[
            "id"
        ]
        assert t["checkers"] == [{"type": "routed_workspace", "workspace": t["kind"]}], t["id"]
        assert t["lane"] == "routing", t["id"]
        assert t["instruction"].endswith("Reply with the single word OK."), t[
            "id"
        ]  # the output cap


def test_the_controls_pass_on_the_gold_route_and_fail_on_a_wrong_route_or_no_trace():
    def run(task, control):
        ctx = CheckContext(
            task=task, final_text=control.get("answer", ""), served=control.get("served")
        )
        return apply_checkers(task, ctx).outcome

    for t in TASKS.values():
        assert run(t, t["controls"]["pass"][0]) == Outcome.PASS, t["id"]
        assert run(t, t["controls"]["fail"][0]) == Outcome.FAIL, t["id"]  # routed to auto-daily
        assert run(t, {}) == Outcome.FAIL, t["id"]  # no served record: the row proves nothing


def test_the_gold_workspace_is_never_named_and_examples_are_kept_out():
    examples = json.loads((REPO / "config/routing_examples.json").read_text())
    shingles = gen._example_shingles()
    for t in TASKS.values():
        assert t["kind"] not in t["instruction"], t["id"]
        for other in gen.PROMPTS:
            assert not re.search(rf"\b{re.escape(other)}\b", t["instruction"]), t["id"]
        assert not (gen._shingles(t["instruction"]) & shingles), t["id"]
        for ex in examples.get("examples", []):
            assert str(ex.get("message", "")).lower() not in t["instruction"].lower(), t["id"]


def test_every_prompt_is_provably_clear_cut_offline():
    """The production Layer 2 fallback resolves every prompt to its gold, and the
    harmful-intent gate stays cold (a trip would reroute the row to auto-daily)."""
    from portal.platform.inference.router import routing as rt

    for t in TASKS.values():
        got = rt._detect_workspace([{"role": "user", "content": t["instruction"]}])
        assert got == t["kind"], (t["id"], got)
        assert not rt.detect_harmful_intent([{"role": "user", "content": t["instruction"]}]), t[
            "id"
        ]


def test_no_instruction_opens_a_sentence_with_a_file_name():
    for t in TASKS.values():
        assert not re.search(
            r"(?:^|[.\n]\s*)In [A-Z0-9][A-Z0-9._-]*\s*[,\u2014]", t["instruction"]
        ), t["id"]


def test_the_suite_regenerates_identically():
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()


def test_the_window_holds_the_prompt_under_the_default_output_budget():
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto"]
    limit = portal["context_limit"]
    assert portal.get("predict_limit") is None  # the harness default 2048 applies
    for t in TASKS.values():
        prompt = (len(portal.get("owui_system_prompt") or "") + len(t["instruction"])) / 4
        assert prompt + 2048 <= limit, (t["id"], prompt + 2048)


def test_the_plan_is_single_arm_on_the_model_hint():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["auto"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto"]
    assert plan["arms"]["incumbent"] == portal["model_hint"]
    assert (
        plan["arms"]["challengers"] == []
    )  # the classifier is LLM_ROUTER_MODEL env, not a parameter
    assert plan["home"] == "routing_production" and plan["discovery"] == []
    assert "tool_mode" not in plan  # no tools on any row
    window = int(re.search(r"ctx(\d+)k", plan["arms"]["incumbent"]).group(1)) * 1024
    assert window >= portal["context_limit"]


def test_the_identity_exemption_covers_exactly_the_routed_rows():
    """campaign.identity_drift skips routed_workspace rows and nothing else: a plain
    row on the same suite still drifts when another seat serves it."""
    from tests.wfe.campaign import _is_routed_row

    r = {"suite_path": str(SUITE), "task_id": "route-coding-00"}
    assert _is_routed_row(r) is True
    assert _is_routed_row({"suite_path": str(SUITE), "task_id": "no-such-task"}) is False
    assert _is_routed_row({"task_id": "route-coding-00"}) is False  # no suite path, no exemption


# --------------------------------------------------------------- attainability


def test_attainability_fails_when_a_prompt_is_not_clear_cut_or_names_a_workspace():
    from tests.wfe.e2e import routing_attainability as att

    gen.build()
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    example_shingles = gen._example_shingles()
    assert all(att.check_task(t, portal, example_shingles) == [] for t in TASKS.values())

    poisoned = json.loads(json.dumps(TASKS["route-coding-00"]))
    poisoned["instruction"] = "Write me a poem about an autumn forest. " + gen.TAIL
    failures = att.check_task(poisoned, portal, example_shingles)
    assert any("Layer 2 resolves the prompt" in f for f in failures), failures

    leaking = json.loads(json.dumps(TASKS["route-coding-00"]))
    leaking["instruction"] = f"Route this to auto-coding please. {gen.TAIL}"
    assert any(
        "names the workspace id" in f for f in att.check_task(leaking, portal, example_shingles)
    )
