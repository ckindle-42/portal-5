"""The extract-uncensored suite: sound under the controls gate, regenerates
identically, every gold computed from the embedded document spec, the documents-suite
lessons enforced, the answers numeric-anchored to their keys, and the plan's arms
served by the lane's backends.yaml groups at >= 8k windows."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_extract_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/extract_production.jsonl"
PLAN = REPO / "tests/wfe/plans/extract_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"entities": 12, "fields": 12, "summary-facts": 12}
IMPERATIVE = {"Extract"}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict) -> dict:
    return json.loads(task["controls"]["pass"][0]["answer"])


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(t["id"].startswith(f"ex-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_no_tools_and_answer_graded():
    for t in TASKS.values():
        assert t["no_tools"] is True and t["requires_tools"] == [] and t["agentic"] is False, t[
            "id"
        ]
        assert [c["type"] for c in t["checkers"]] == ["answer_contains"], t["id"]
        assert t["lane"] == "extract", t["id"]


def test_the_controls_pass_and_fail_where_they_must():
    def run(task, answer):
        ctx = CheckContext(task=task, final_text=answer)
        return apply_checkers(task, ctx).outcome

    for t in TASKS.values():
        good = t["controls"]["pass"][0]["answer"]
        assert run(t, good) == Outcome.PASS, t["id"]
        assert run(t, t["controls"]["fail"][0]["answer"]) == Outcome.FAIL, t["id"]
        assert run(t, "") == Outcome.FAIL, t["id"]  # the harness auto-control


def test_the_gold_values_come_from_the_embedded_document():
    """Extraction, not recall: every gold value appears in the supplied document."""
    for t in TASKS.values():
        ins = t["instruction"]
        doc = ins.split("--- fictional document ---")[-1].split("--- end of document ---")[0]
        assert doc.strip(), t["id"]
        gold = _gold(t)
        values = gold.get("entities") or list(gold.values())
        for v in values:
            assert str(v) in doc, (t["id"], v)


def test_numeric_expects_are_anchored_to_their_keys_not_bare_substrings():
    for t in _kind("summary-facts"):
        pattern = t["checkers"][0]["patterns"][0]
        assert pattern.startswith('"open_actions"'), t["id"]
        gold = _gold(t)
        assert rf'"open_actions"\s*:\s*"?{gold["open_actions"]}"?' in pattern, t["id"]
    for t in _kind("fields"):
        for p in t["checkers"][0]["patterns"]:
            assert re.match(r'"(severity|owner|customer_data)"', p), t["id"]


def test_no_instruction_opens_a_sentence_with_a_file_name_and_the_doc_is_marked_fictional():
    for t in TASKS.values():
        assert not re.search(
            r"(?:^|[.\n]\s*)In [A-Z0-9][A-Z0-9._-]*\s*[,\u2014]", t["instruction"]
        ), t["id"]
        assert "fictional document" in t["instruction"], t["id"]


def test_the_golds_are_unique_across_the_suite():
    golds = [t["controls"]["pass"][0]["answer"] for t in TASKS.values()]
    assert len(golds) == len(set(golds))


def test_deciding_facts_are_declared_and_stated_in_the_instruction():
    gen.build()
    for t in TASKS.values():
        facts = gen.DECIDING_FACTS[t["id"]]
        assert facts, t["id"]
        for f in facts:
            assert f.tool == "" and not f.args, (t["id"], f.why)
            assert re.search(f.pattern, t["instruction"], re.I | re.S), (t["id"], f.why)


def test_the_suite_regenerates_identically():
    built = "".join(json.dumps(t) + "\n" for t in gen.build())
    assert built == SUITE.read_text()


def test_the_chain_fits_the_window_under_the_default_output_budget():
    from portal.platform.inference.config import effective_workspace

    workspaces = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    portal = effective_workspace(workspaces, "auto-documents::extract-uncensored")
    limit = portal["context_limit"]
    assert portal.get("predict_limit") is None  # the harness default 2048 applies
    for t in TASKS.values():
        prompt = (len(portal.get("owui_system_prompt") or "") + len(t["instruction"])) / 4
        assert prompt + 2048 <= limit, (t["id"], prompt + 2048)


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    from portal.platform.inference.config import effective_workspace

    plan = yaml.safe_load(PLAN.read_text())["workloads"]["auto-documents::extract-uncensored"]
    workspaces = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    portal = effective_workspace(workspaces, "auto-documents::extract-uncensored")
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["auto-documents"])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert portal["model_hint"] in [arms["incumbent"], *arms["challengers"]]
    assert plan["home"] == "extract_production"
    assert plan["discovery"] == [] and "tool_mode" not in plan  # no tools: no mode to declare
    assert len(arms["challengers"]) == 3
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], (tag, window)


# --------------------------------------------------------------- attainability


def test_attainability_flags_a_missing_fact_and_gold_drift():
    from portal.platform.inference.config import effective_workspace
    from tests.wfe.e2e import extract_attainability as att

    gen.build()
    workspaces = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    portal = effective_workspace(workspaces, "auto-documents::extract-uncensored")
    built = {t["id"]: _gold(t) for t in TASKS.values()}
    assert all(att.check_task(t, portal, built) == [] for t in TASKS.values())

    truncated = json.loads(json.dumps(TASKS["ex-fields-00"]))
    truncated["instruction"] = 'Extract the fields. Answer only as JSON {"severity": "..."}.'
    assert any(
        "fact not in the embedded document" in f for f in att.check_task(truncated, portal, built)
    )

    drifted = dict(built)
    drifted["ex-fields-00"] = {"severity": "low", "owner": "x", "customer_data": "yes"}
    assert any("gold drift" in f for f in att.check_task(TASKS["ex-fields-00"], portal, drifted))
