"""Session-based intake for new projects — the harness conducts a Q/A session.

Each turn is one CLI call: the operator's answer is written to disk and a fast
MoE decides the next question or, when it has enough, synthesizes and writes the
scaffold. A skill/command in OpenCode/Pi relays questions and answers. No
input() blocking — the session state lives in <project>/.brh/intake.json, so a
human or an agent can drive it identically.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from . import llm as llm_mod
from .llm import LLMConfig
from .workspace import init_project

logger = logging.getLogger(__name__)

_OPENING = "What are you researching, and where are the artifacts (paths or a short description)?"
_MAX_QUESTIONS = 6

_STEP_SYSTEM = (
    "You conduct a short intake for a static binary-research task. Given the Q/A so far, "
    "decide whether you have enough to define: the goal, initial hypotheses, what 'done' "
    "means, and at least two verifier oracles (concrete pass/fail checks). Output ONLY a "
    'JSON object: {"done": bool, "next_question": string|null, "plan": {"goal": string, '
    '"hypotheses": [string], "checks": [string], "verifiers": [{"name": string, '
    '"description": string}]}|null}. Ask at most ONE concrete question at a time. Set '
    "done=true (with plan filled, next_question=null) as soon as you can define the task."
)


@dataclass
class ScaffoldPlan:
    goal: str
    hypotheses: list[str]
    checks: list[str]
    verifiers: list[dict]


def _state_path(project_dir: Path) -> Path:
    return project_dir / ".brh" / "intake.json"


def _default_state() -> dict:
    return {
        "state": "asking",
        "turns": [],
        "pending_question": None,
        "opening_asked": False,
        "scaffold_written": False,
    }


def load_state(project_dir: Path) -> dict:
    p = _state_path(project_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return _default_state()
    return _default_state()


def _save(project_dir: Path, st: dict) -> None:
    p = _state_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=2))


def _parse_json(text: str | None, default):
    if not text:
        return default
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t else t
        t = t.removeprefix("json").strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(t[start : end + 1])
            except json.JSONDecodeError:
                return default
        return default


def _fallback_goal(turns: list[dict]) -> str:
    for t in turns:
        if t.get("a"):
            return f"Reconstruct how the artifacts work. Operator note: {t['a']}"
    return "Reconstruct how the artifacts in artifacts/ work. Do not execute them."


def start(project_dir: Path) -> dict:
    """Begin (or resume) the intake session. Returns the current turn state."""
    init_project(project_dir)
    st = load_state(project_dir)
    if not st["opening_asked"]:
        st["pending_question"] = _OPENING
        st["opening_asked"] = True
        _save(project_dir, st)
    return {"state": st["state"], "question": st["pending_question"]}


def _next_step(config: LLMConfig, turns: list[dict]) -> dict:
    qa = "\n".join(f"Q: {t['q']}\nA: {t['a']}" for t in turns)
    raw = None
    try:
        resp = llm_mod.complete(
            config, [{"role": "system", "content": _STEP_SYSTEM}, {"role": "user", "content": qa}]
        )
        raw = resp.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("intake model call failed: %s", exc)
    return _parse_json(raw, default={}) or {}


def answer(config: LLMConfig, project_dir: Path, text: str) -> dict:
    """Record an answer, then either emit the next question or write the scaffold."""
    st = load_state(project_dir)
    if not st["opening_asked"] or st["pending_question"] is None:
        start(project_dir)
        st = load_state(project_dir)
    st["turns"].append({"q": st["pending_question"], "a": text})
    st["pending_question"] = None
    _save(project_dir, st)

    forced = len(st["turns"]) >= _MAX_QUESTIONS
    step = _next_step(config, st["turns"])
    done = bool(step.get("done")) or forced

    if not done and step.get("next_question"):
        st["pending_question"] = step["next_question"]
        _save(project_dir, st)
        return {"state": "asking", "question": st["pending_question"]}

    plan_raw = step.get("plan") or {}
    plan = ScaffoldPlan(
        goal=plan_raw.get("goal") or _fallback_goal(st["turns"]),
        hypotheses=plan_raw.get("hypotheses") or [],
        checks=plan_raw.get("checks") or [],
        verifiers=plan_raw.get("verifiers") or [],
    )
    apply_plan(project_dir, plan)
    st["state"] = "ready"
    st["scaffold_written"] = True
    _save(project_dir, st)
    return {
        "state": "ready",
        "goal": plan.goal,
        "verifiers": len(plan.verifiers),
        "hint": "Add artifacts to artifacts/, make the verifier stubs real, then confirm to run.",
    }


def status(project_dir: Path) -> dict:
    return load_state(project_dir)


def apply_plan(project_dir: Path, plan: ScaffoldPlan) -> None:
    """Write the plan into the project's static structure."""
    init_project(project_dir)
    (project_dir / "GOAL.txt").write_text(plan.goal.strip() + "\n")
    if plan.hypotheses:
        body = "# 01_hypotheses\n\n" + "\n".join(
            f"{i}. {h}" for i, h in enumerate(plan.hypotheses, 1)
        )
        (project_dir / "01_hypotheses.md").write_text(body + "\n")
    if plan.checks:
        body = "# 04_checks\n\n" + "\n".join(f"- {c}" for c in plan.checks)
        (project_dir / "04_checks.md").write_text(body + "\n")
    for i, v in enumerate(plan.verifiers[:6], 1):
        name = "".join(ch if ch.isalnum() else "_" for ch in str(v.get("name", f"check_{i}")))[:40]
        desc = str(v.get("description", "")).replace("\n", " ")
        stub = (
            "#!/usr/bin/env bash\n"
            f"# VERIFIER STUB: {desc}\n"
            "# Fill in the oracle. Exit 0 on PASS, non-zero on FAIL.\n"
            'JOB_DIR="${JOB_DIR:-.}"\n'
            f'echo "TODO: implement {name}"\n'
            "exit 1\n"
        )
        path = project_dir / "verifiers" / f"{name}.sh"
        if not path.exists():
            path.write_text(stub)
            path.chmod(0o755)
