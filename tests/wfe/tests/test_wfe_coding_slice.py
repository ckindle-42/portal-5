"""auto-coding's production suite: sound under the controls gate, every reference solution passes
its hidden tests and the seeded repo does not, the visible tests behave as stated, nothing a tool
can reach holds the reference, and the decision plan's arms are served and fit the window."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

from tests.wfe import controls
from tests.wfe.checkers import GRADED_ROOT, CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_coding_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/coding_production.jsonl"
PLAN = REPO / "tests/wfe/plans/coding_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
FILE_GRADED = [t for t in TASKS.values() if t["kind"] != "read"]


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _grade(task: dict, files: dict[str, str]):
    with tempfile.TemporaryDirectory() as td:
        for rel, text in files.items():
            (Path(td) / rel).write_text(text)
        return apply_checkers(
            task, CheckContext(task=task, final_text="", tool_calls=[], sandbox_root=Path(td))
        )


def _pytest(files: dict[str, str]) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        for rel, text in files.items():
            (Path(td) / rel).write_text(text)
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--import-mode=importlib",
            ],
            capture_output=True,
            text=True,
            cwd=td,
            timeout=120,
        )


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in gen.COUNTS.items():
        assert len(_kind(kind)) == n, kind
        assert sum(t["screen"] for t in _kind(kind)) == gen.SCREEN[kind], kind
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())
    assert all(t["lane"] == "coding" and t.get("repo_read") is False for t in TASKS.values())


def test_every_task_is_graded_by_hidden_tests_or_by_answer_and_trace():
    for t in _kind("read"):
        assert [c["type"] for c in t["checkers"]] == ["answer_contains", "tool_grounded"]
    for t in _kind("implement"):
        assert [c["type"] for c in t["checkers"]] == ["hidden_pytest"]
    for t in _kind("fix") + _kind("refactor"):
        assert [c["type"] for c in t["checkers"]] == ["immutable", "hidden_pytest"]
    for t in FILE_GRADED:
        spec = next(c for c in t["checkers"] if c["type"] == "hidden_pytest")
        assert (GRADED_ROOT / spec["graded"]).is_dir() and spec["min_passed"] >= 4, t["id"]


@pytest.mark.parametrize("task", FILE_GRADED, ids=lambda t: t["id"])
def test_the_reference_passes_the_hidden_tests_and_the_seed_alone_does_not(task):
    gen.build()
    ref = _grade(task, {**(task.get("seed") or {}), **gen.REFERENCES[task["id"]]})
    assert ref.outcome == Outcome.PASS, ref.notes
    base = _grade(task, dict(task.get("seed") or {}))
    assert base.outcome == Outcome.FAIL, "the task is already solved by its seed"


@pytest.mark.parametrize("task", _kind("fix") + _kind("refactor"), ids=lambda t: t["id"])
def test_a_tampered_visible_test_fails_the_immutable_checker(task):
    gen.build()
    module = next(iter(gen.REFERENCES[task["id"]])).removesuffix(".py")
    files = {
        **task["seed"],
        **gen.REFERENCES[task["id"]],
        f"test_{module}.py": "def test_x():\n    pass\n",
    }
    res = _grade(task, files)
    assert res.outcome == Outcome.FAIL and "tampered" in res.notes


@pytest.mark.parametrize("task", _kind("fix") + _kind("refactor"), ids=lambda t: t["id"])
def test_the_visible_tests_fail_on_a_fix_seed_and_pass_on_a_refactor_seed_and_the_reference(task):
    gen.build()
    module = next(iter(gen.REFERENCES[task["id"]])).removesuffix(".py")
    seed_run = _pytest(task["seed"])
    if task["kind"] == "fix":
        assert seed_run.returncode != 0, "the visible test passes on the buggy seed"
    else:
        assert seed_run.returncode == 0, seed_run.stdout[-400:]
    fixed = {f"test_{module}.py": task["seed"][f"test_{module}.py"], **gen.REFERENCES[task["id"]]}
    assert _pytest(fixed).returncode == 0


def test_no_distinctive_reference_line_is_reachable_by_a_tool_or_the_prompt():
    gen.build()
    for t in FILE_GRADED:
        seeded = "\n".join((t.get("seed") or {}).values())
        seeded_lines = {x.strip() for x in seeded.splitlines()}
        visible = t["instruction"] + "\n" + seeded
        for src in gen.REFERENCES[t["id"]].values():
            for line in {x.strip() for x in src.splitlines()} - seeded_lines:
                if len(line) > 14 and not line.startswith(("def ", "class ")):
                    assert line not in visible, (t["id"], line)
    # the hidden tests live under tests/wfe/, which the sandbox never reads (and repo_read is off)
    from tests.wfe.runner import _repo_denied

    assert _repo_denied("tests/wfe/graded/cp_fix_00/test_stats.py")
    assert all((GRADED_ROOT / "cp_implement_00").glob("test_*.py"))


def test_read_golds_are_recomputed_independently_and_never_stated():
    for t in _kind("read"):
        module = next(iter(t["seed"])).removesuffix(".py")
        ns: dict = {}
        exec(t["seed"][f"{module}.py"], ns)  # noqa: S102 - generator-controlled fixture
        expr = next(r for r in gen.READ if r[1] == module)[3]
        value, exc = gen.run_snippet(ns, f"result = {expr}")
        gold = json.loads(t["controls"]["pass"][0]["answer"])["answer"]
        assert gold == (exc or str(value)), t["id"]
        body = t["instruction"].replace(gen.FORMAT, "")
        assert not re.search(rf"(?<![\w.]){re.escape(gold)}(?![\w])", body), t["id"]


def test_a_third_of_the_read_tasks_are_imperative_and_the_rest_questions():
    starts = [t["instruction"].split()[0] for t in _kind("read")]
    assert starts.count("Read") * 3 >= len(starts) - 1 and "In" in starts


def _read_outcome(task: dict, answer: str, calls: list) -> Outcome:
    return apply_checkers(
        task, CheckContext(task=task, final_text=answer, tool_calls=calls)
    ).outcome


def test_the_controls_for_read_tasks_pass_with_a_trace_only():
    for t in _kind("read"):
        good, calls = t["controls"]["pass"][0]["answer"], t["controls"]["pass"][0]["tool_calls"]
        assert _read_outcome(t, good, calls) == Outcome.PASS
        assert _read_outcome(t, good, []) == Outcome.FAIL
        assert _read_outcome(t, t["controls"]["fail"][1]["answer"], calls) == Outcome.FAIL


def test_the_suite_and_hidden_tests_regenerate_identically():
    before = {p: p.read_text() for p in GRADED_ROOT.glob("cp_*/test_*.py")}
    try:
        built = "".join(json.dumps(t) + "\n" for t in gen.build())
        assert built == SUITE.read_text()
        assert {p: p.read_text() for p in GRADED_ROOT.glob("cp_*/test_*.py")} == before
    finally:
        for p, text in before.items():
            p.write_text(text)


def test_the_plan_arms_are_served_fit_the_window_and_exclude_laguna():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["auto-coding"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto-coding"]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["auto-coding"])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert arms["incumbent"] == portal["model_hint"] and plan["tool_mode"] == "sandbox"
    assert len(arms["challengers"]) == 3
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served, tag
        assert "laguna" not in tag.lower()
        assert int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024 >= 65536, tag
    modes = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    assert "auto-coding" not in modes  # the sandbox family: no production allowlist


def test_the_attainability_script_flags_an_unsolvable_or_already_solved_task(monkeypatch):
    from tests.wfe.e2e import coding_attainability as att

    gen.build()
    task = TASKS["code-fix-00"]
    assert att.check_task(task) == []
    monkeypatch.setitem(
        gen.REFERENCES, task["id"], {"stats.py": "def mean_of_top(v, n):\n    return 0\n"}
    )
    assert any("reference does not pass" in f for f in att.check_task(task))
    solved = {**task, "seed": {**task["seed"], "stats.py": gen.REFERENCES[task["id"]]["stats.py"]}}
    monkeypatch.setitem(gen.REFERENCES, task["id"], {})
    monkeypatch.undo()
    gen.build()
    solved["seed"]["stats.py"] = gen.REFERENCES[task["id"]]["stats.py"]
    assert any("already passes" in f for f in att.check_task(solved))
