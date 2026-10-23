"""The security-analysis production suite: sound under the controls gate, regenerates
identically, every gold checkable in code, no gold stated in the instruction, deciding
facts declared and present, and the plan's arms served by auto-security's backends.yaml
groups at >= 8k windows."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_security_analysis_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/security_analysis_production.jsonl"
PLAN = REPO / "tests/wfe/plans/security_analysis_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"cve-cwe": 12, "severity": 12, "vulnerable-function": 12}
WORKSPACE = "auto-security"
IMPERATIVE = {"Classify", "Report", "Identify"}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n, kind
        assert all(t["id"].startswith(f"sa-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_no_tools_and_answer_graded():
    for t in TASKS.values():
        assert t["no_tools"] is True and t["requires_tools"] == [] and t["agentic"] is False, t[
            "id"
        ]
        assert [c["type"] for c in t["checkers"]] == ["answer_contains"], t["id"]
        assert t["lane"] == "security", t["id"]


def test_the_controls_pass_and_fail_where_they_must():
    def run(task, answer):
        ctx = CheckContext(task=task, final_text=answer)
        return apply_checkers(task, ctx).outcome

    for t in TASKS.values():
        good = t["controls"]["pass"][0]["answer"]
        assert run(t, good) == Outcome.PASS, t["id"]
        assert run(t, t["controls"]["fail"][0]["answer"]) == Outcome.FAIL, t["id"]
        assert run(t, "") == Outcome.FAIL, t["id"]


def test_the_instruction_never_states_the_gold():
    for t in TASKS.values():
        assert _gold(t) not in t["instruction"], t["id"]


def test_golds_are_unique_within_each_kind_except_severity():
    # Severity bands naturally repeat across CVEs; the other two kinds must not
    # duplicate their gold CWE ids within the kind.
    for kind in ("cve-cwe", "vulnerable-function"):
        golds = [_gold(t) for t in _kind(kind)]
        assert len(golds) == len(set(golds)), (kind, sorted(golds))
    bands = {_gold(t) for t in _kind("severity")}
    assert len(bands) >= 3, bands


def test_deciding_facts_are_declared_and_stated():
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


def test_the_prompt_fits_the_window_under_the_hard_output_cap():
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][WORKSPACE]
    limit = portal["context_limit"]
    cap = portal.get("predict_limit") or 2048
    assert cap and limit
    for t in TASKS.values():
        prompt = (len(portal.get("owui_system_prompt") or "") + len(t["instruction"])) / 4
        assert prompt + cap <= limit, (t["id"], prompt + cap)


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"][WORKSPACE]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][WORKSPACE]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    assert plan["home"] == "security_analysis_production" and plan["discovery"] == []
    assert "tool_mode" not in plan
    groups = set(backends["workspace_routing"][WORKSPACE])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert arms["incumbent"] == portal["model_hint"]
    assert len(arms["challengers"]) == 2
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], (tag, window)


def test_a_third_of_each_kind_is_imperative():
    for kind in KINDS:
        starts = [t["instruction"].split()[0] for t in _kind(kind)]
        imperative = sum(w in IMPERATIVE for w in starts)
        assert imperative * 3 >= len(starts) - 1, (kind, starts)


# --------------------------------------------------------------- attainability


def test_attainability_flags_a_missing_given_a_stated_gold_and_gold_drift():
    from tests.wfe.e2e import security_analysis_attainability as att

    gen.build()
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    built = {t["id"]: _gold(t) for t in TASKS.values()}
    assert all(att.check_task(t, portal, built) == [] for t in TASKS.values())

    truncated = json.loads(json.dumps(TASKS["sa-cve-cwe-00"]))
    truncated["instruction"] = 'What CWE id does NVD assign? Answer only as JSON {"answer": "..."}.'
    assert any("given not stated" in f for f in att.check_task(truncated, portal, built))

    leaked = json.loads(json.dumps(TASKS["sa-cve-cwe-00"]))
    leaked["instruction"] += f" The answer is {_gold(TASKS['sa-cve-cwe-00'])}."
    assert any("gold not private" in f for f in att.check_task(leaked, portal, built))

    drifted = dict(built)
    drifted["sa-cve-cwe-00"] = "CWE-999"
    assert any("gold drift" in f for f in att.check_task(TASKS["sa-cve-cwe-00"], portal, drifted))


# ----------------------------------------------------------- accepted answer sets


def _answers(task: dict, *values: str) -> list[Outcome]:
    return [
        apply_checkers(task, CheckContext(task=task, final_text=json.dumps({"answer": v}))).outcome
        for v in values
    ]


def test_defensible_parent_and_sibling_cwes_are_accepted_and_nothing_else():
    by_label = {label: (n, cwes) for n, (label, _, cwes) in enumerate(gen.VULN_SNIPPETS)}
    expect = {
        "buffer-overflow": {"CWE-121", "CWE-120", "CWE-787"},
        "weak-hash": {"CWE-328", "CWE-327", "CWE-916"},
        "information-exposure": {"CWE-200", "CWE-209"},
        "hardcoded-credentials": {"CWE-798", "CWE-259"},
    }
    for label, accepted in expect.items():
        n, cwes = by_label[label]
        task = TASKS[f"sa-vulnerable-function-{n:02d}"]
        assert set(cwes) == accepted, label
        assert set(_answers(task, *sorted(accepted))) == {Outcome.PASS}, label
        assert _answers(task, "CWE-89", "CWE-1210") == [Outcome.FAIL, Outcome.FAIL], label


def test_the_cve_items_use_nvd_primary_data_and_the_reworded_question():
    assert len({c for c, *_ in gen.CVE_ITEMS}) == 12 and gen.CVE_ITEMS[0][0] != "CVE-2026-0001"
    for t in _kind("cve-cwe"):
        assert (
            "recorded for CVE-" in t["instruction"] and "(CNA-provided or NVD)" in t["instruction"]
        )
    for _cve, cwes, severity, published in gen.CVE_ITEMS:
        assert cwes and severity in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert published >= "2026-01-01"


def test_the_two_replaced_snippets_have_one_answer_and_no_second_weakness():
    labels = {label: cwes for label, _, cwes in gen.VULN_SNIPPETS}
    assert labels["cross-site-request-forgery"] == ("CWE-352",)
    assert labels["server-side-request-forgery"] == ("CWE-918",)
    assert "improper-access-control" not in labels and "missing-authorization" not in labels
    for label, snippet, _ in gen.VULN_SNIPPETS:
        assert "SELECT" not in snippet.upper() or label == "sql-injection", label
