"""The reading-narrow suite: sound under the controls gate, regenerates identically,
carries compliance_production's gold unmodified (PLANT keys forbidden in tool output),
graded on the answer and the trace, the documents-suite lessons enforced (no file as a
sentence-opener; numeric expectations anchored to their key and unit), the allowlist a
subset of both the workspace's own tools and the evaluation instance's VERIFIED_TOOLS,
and the plan's arms served by the lane's backends.yaml group at >= 128k windows."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_compliance_production as comp
from tests.wfe.suites import build_reading_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/reading_production.jsonl"
PLAN = REPO / "tests/wfe/plans/reading_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"determination": 12, "lookup": 24}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


# --------------------------------------------------------------- suite gates


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(
            t["id"].startswith(f"read-{'det' if kind == 'determination' else 'lookup'}")
            for t in _kind(kind)
        )
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_graded_on_its_answer_and_on_its_trace():
    for t in TASKS.values():
        kinds = [c["type"] for c in t["checkers"]]
        assert kinds == ["answer_contains", "tool_grounded"], t["id"]
        assert t["lane"] == "reading" and t["agentic"] is True, t["id"]
        for c in t["checkers"][0].get("forbid_in_tool_output") or []:
            assert c in comp.LEAKS, (t["id"], c)
    for t in _kind("determination"):
        assert t["requires_tools"] == ["compliance_read"], t["id"]
    for t in _kind("lookup"):
        assert t["requires_tools"] == ["nerc_cip_requirement"], t["id"]
        assert set(t["checkers"][1]["tools"]) <= set(comp.LOOKUP_TOOLS), t["id"]


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


def test_no_instruction_opens_a_sentence_with_a_file_name():
    """The documents-suite lesson: 'In terms.docx, ...' was read as the filename.
    A document is named as 'the operator corpus document <id>', never 'In <id>,'."""
    for t in TASKS.values():
        assert not re.search(
            r"(?:^|[.\n]\s*)In [A-Z0-9][A-Z0-9._-]*\s*[,\u2014]", t["instruction"]
        ), t["id"]
        assert not re.search(r"In \w+\.(?:md|docx|pdf|xlsx)\b", t["instruction"]), t["id"]


def test_numeric_expectations_are_anchored_not_bare_substrings():
    """A lookup's interval is graded inside its "interval" key WITH its unit; a bare
    digit pattern (like /3/) would match any number containing it."""
    for t in _kind("lookup"):
        pattern = t["checkers"][0]["patterns"][0]
        gold = json.loads(t["controls"]["pass"][0]["answer"])
        num, _, unit = gold["interval"].partition(" ")
        assert pattern.startswith('"interval"'), t["id"]
        assert rf"\b{num}\b" in pattern, t["id"]  # the digit, word-bounded
        assert unit.split()[-1] in pattern, t["id"]  # the unit anchors it
        assert not re.fullmatch(r"\\b\d+\\b", pattern), t["id"]  # never a bare digit
    for t in _kind("determination"):
        for p in t["checkers"][0]["patterns"]:
            assert p.startswith('"coverage"') or p.startswith('"signal"'), t["id"]


def test_the_gold_is_never_stated_and_the_answer_key_is_forbidden_in_tool_output():
    for t in TASKS.values():
        assert not any(
            k in t["instruction"] for k in ("expected_coverage", "expected_signal", "PLANT")
        ), t["id"]
    for t in _kind("determination"):
        assert t["checkers"][0]["forbid_in_tool_output"] == comp.LEAKS, t["id"]


def test_the_suite_regenerates_identically():
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()


def test_the_reading_subset_is_within_the_workspace_and_the_eval_instance():
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    allow = set(modes["compliance-reading"]["allow"])
    portal_tools = set(
        yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
            "compliance-reading"
        ]["tools"]
    )
    from portal.modules.compliance.core.eval_instance import VERIFIED_TOOLS

    assert allow <= portal_tools, allow - portal_tools
    assert allow <= set(VERIFIED_TOOLS), allow - set(VERIFIED_TOOLS)
    assert not allow & {"compliance_note", "compliance_correct", "compliance_review_decide"}
    for t in TASKS.values():
        assert set(t["requires_tools"]) <= allow, t["id"]


def test_the_window_is_generous_but_checked():
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
        "compliance-reading"
    ]
    limit, cap = portal["context_limit"], portal["predict_limit"]
    assert cap and limit
    for t in TASKS.values():
        prompt = (len(portal.get("owui_system_prompt") or "") + len(t["instruction"])) / 4
        assert prompt + cap <= limit, (t["id"], prompt + cap)


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["compliance-reading"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
        "compliance-reading"
    ]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["compliance-reading"])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert arms["incumbent"] == portal["model_hint"] and plan["tool_mode"] == "production"
    assert plan["home"] == "reading_production" and plan["discovery"] == []
    assert len(arms["challengers"]) == 3
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], (tag, window)


# --------------------------------------------------------------- attainability


def test_attainability_fails_when_a_fact_is_not_exposed_and_passes_on_the_trace():
    from tests.wfe.e2e import reading_attainability as att

    gen.build()

    def silent(tool, args):
        return json.dumps(
            {"parts": [{"id": args.get("req_id"), "verbatim_text": "no interval here"}]}
        )

    lookup = next(t for t in _kind("lookup"))
    assert any("fact not exposed" in f for f in att.check_task(lookup, silent)), lookup["id"]

    def replays_the_trace(tool, args):
        for c in lookup["controls"]["pass"][0]["tool_calls"]:
            if c["name"] == tool and c["args"] == args:
                return c["output"]
        return json.dumps({"parts": [{"id": lookup["controls"]["pass"][0]["answer"]}]})

    assert att.check_task(lookup, replays_the_trace) == []


def test_determination_attainability_delegates_to_the_compliance_check():
    from tests.wfe.e2e import reading_attainability as att

    gen.build()
    det = next(t for t in _kind("determination"))
    gold = json.loads(det["controls"]["pass"][0]["answer"])

    def replays_the_trace(tool, args):
        for c in det["controls"]["pass"][0]["tool_calls"]:
            if c["name"] == tool and c["args"] == args:
                return c["output"]
        return json.dumps({"sections_in_standard": 4, "text": "== " + "x" * 40})

    failures = att.check_task(det, replays_the_trace)
    assert any("fact not exposed" in f for f in failures), (
        gold
    )  # the real doc text is not in the stub
    assert att.check_task.__doc__  # delegation documented
