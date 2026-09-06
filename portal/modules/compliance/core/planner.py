"""The planner and the twelve questions (TASK_COMPLIANCE_REASONING_V6 P7).

An operator question is mapped onto an **operation plan** — an ordered list of
the six primitives with their arguments — which is then executed, each step
recording the evidence it produced. The plan *is* the trace (Y18): no answer is
composed from an operation that did not run.

The twelve questions of §4 are the plan templates. A deterministic classifier
picks the template from the question text (cue scoring, same shape as
``engine.classify_intent``); a model may override via ``planner_fn`` but never
invents a step outside the six ops. The composed answer is produced from the
recorded step evidence, cited.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# question id -> ordered ops (the §4 compositions)
QUESTION_PLANS: dict[str, list[str]] = {
    "Q01": ["resolve"],
    "Q02": ["trace"],
    "Q03": ["resolve", "judge"],
    "Q04": ["judge"],
    "Q05": ["diff"],
    "Q06": ["trace", "trace"],
    "Q07": ["judge", "propose", "judge"],
    "Q08": ["norms"],
    "Q09": ["norms"],
    "Q10": ["trace"],
    "Q11": ["diff", "trace"],
    "Q12": ["propose", "judge", "trace"],
}

_Q_CUES: dict[str, list[str]] = {
    "Q01": [r"what does .*require", r"what.*actually require", r"current requirement"],
    "Q02": [r"which of our (policies|procedures)", r"what.*implement it", r"how do we implement"],
    "Q03": [r"fully aligned", r"aligned with the latest", r"are our .*procedures .*aligned"],
    "Q04": [r"where are (the )?gaps", r"gaps.*inconsisten", r"outdated language", r"no longer map"],
    "Q05": [r"has (a|the) requirement changed", r"changed since", r"since .*(written|reviewed)"],
    "Q06": [
        r"if we (modify|change) a procedure",
        r"what .*could be affected",
        r"impact of (editing|changing)",
    ],
    "Q07": [r"what changes would bring", r"better align", r"how (do|can) we (fix|close)"],
    "Q08": [r"more restrictive than required", r"stricter than", r"are we over-?compliant"],
    "Q09": [
        r"permit flexibility",
        r"flexibility .*not use",
        r"where does the regulation (allow|permit)",
    ],
    "Q10": [
        r"what (documents|controls|evidence|systems|roles).*connect",
        r"connect to a requirement",
    ],
    "Q11": [
        r"new or revised standard becomes effective",
        r"future.?effective",
        r"which .*documents need review",
    ],
    "Q12": [
        r"how should a proposed change be implemented",
        r"implement .*maintaining compliance",
        r"change package",
    ],
}


@dataclass
class PlanStep:
    op: str
    args: dict[str, Any]
    evidence: Any = None  # filled at execution time
    ran: bool = False


@dataclass
class AnswerTrace:
    question: str
    question_id: str
    steps: list[PlanStep] = field(default_factory=list)
    answer: str = ""
    citations: list[str] = field(default_factory=list)
    sme_decision_kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "question_id": self.question_id,
            "operation_plan": [{"op": s.op, "args": s.args, "ran": s.ran} for s in self.steps],
            "answer": self.answer,
            "citations": self.citations,
            "sme_decision_kind": self.sme_decision_kind,
        }


def classify_question(question: str) -> str:
    q = question.lower()
    scores = {qid: sum(bool(re.search(p, q)) for p in pats) for qid, pats in _Q_CUES.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] else "Q01"


PlannerFn = Callable[[str], str]  # question -> question_id


def plan_question(
    question: str, *, planner_fn: PlannerFn | None = None
) -> tuple[list[PlanStep], str]:
    qid = (planner_fn or classify_question)(question)
    if qid not in QUESTION_PLANS:
        qid = classify_question(question)
    return [PlanStep(op=op, args={}) for op in QUESTION_PLANS[qid]], qid


def execute_plan(
    question: str,
    ref: str,
    *,
    op_impls: dict[str, Callable[..., Any]],
    op_args: dict[str, dict[str, Any]] | None = None,
    planner_fn: PlannerFn | None = None,
) -> AnswerTrace:
    """Run the plan for ``question`` about ``ref``. ``op_impls`` maps an op
    name to a callable; ``op_args`` supplies per-op keyword arguments. Each
    step records what it produced — an answer composed from a step that did
    not run is impossible by construction (Y18)."""
    steps, qid = plan_question(question, planner_fn=planner_fn)
    trace = AnswerTrace(question=question, question_id=qid, steps=steps)
    op_args = op_args or {}
    for step in steps:
        impl = op_impls.get(step.op)
        if impl is None:
            step.evidence = {"error": f"no implementation for op {step.op!r}"}
            continue
        step.args = {"ref": ref, **op_args.get(step.op, {})}
        step.evidence = impl(**step.args)
        step.ran = True
        _collect_citations(step, trace)
        _collect_sme(step, trace)
    return trace


def _collect_citations(step: PlanStep, trace: AnswerTrace) -> None:
    ev = step.evidence
    for attr in ("citations", "reference_closure"):
        val = getattr(ev, attr, None) if not isinstance(ev, dict) else ev.get(attr)
        if isinstance(val, list):
            trace.citations = sorted(set(trace.citations) | {str(x) for x in val})
    ref = getattr(ev, "ref", None) or (ev.get("ref") if isinstance(ev, dict) else None)
    anchor = getattr(ev, "anchor", None)
    for x in (ref, anchor):
        if x:
            trace.citations = sorted(set(trace.citations) | {str(x)})


def _collect_sme(step: PlanStep, trace: AnswerTrace) -> None:
    kind = getattr(step.evidence, "sme_decision_kind", "")
    if kind:
        trace.sme_decision_kind = kind


def compose_answer(
    trace: AnswerTrace, *, composer_fn: Callable[[AnswerTrace], str] | None = None
) -> str:
    if composer_fn is not None:
        trace.answer = composer_fn(trace)
        return trace.answer
    lines = [f"[{trace.question_id}] plan: {' -> '.join(s.op for s in trace.steps)}"]
    for s in trace.steps:
        head = f"  {s.op}"
        ev = s.evidence
        det = getattr(ev, "determination", None)
        if det:
            lines.append(f"{head}: {det} ({getattr(ev, 'finding_type', '') or 'no finding'})")
        elif hasattr(ev, "label"):
            lines.append(f"{head}: {ev.label}; {len(getattr(ev, 'actor_cus', []))} actor-CU(s)")
        elif hasattr(ev, "nodes"):
            lines.append(f"{head}: {len(ev.nodes)} node(s), frontier {len(ev.frontier)}")
        else:
            lines.append(f"{head}: done")
    if trace.sme_decision_kind:
        lines.append(f"  SME: {trace.sme_decision_kind}")
    lines.append(f"  citations: {', '.join(trace.citations) or '(none)'}")
    trace.answer = "\n".join(lines)
    return trace.answer
