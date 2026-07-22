"""Failure-attribution for blue-orchestration ablation runs.

Turns one (arm, scenario) OrchestrationResult + its scoring into a single
diagnosis class, so the corpus aggregate can ROUTE the next build (retrieval
vs budget vs council) instead of guessing. Hermetic: operates on plain dicts
(trace + scoring + ground truth), no live calls. Proven on fixtures (I9).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# Outcome of one (arm, scenario). HIT / NOVELTY are successes; the rest are the
# miss taxonomy the decision rule aggregates over.
OUTCOMES = ["HIT", "NOVELTY", "HUNTER_MISS", "HANDOFF_LOSS", "HALLUCINATION", "NON_CONVERGENCE"]

# Miss categories only (successes excluded) — the decision rule's histogram domain.
MISS_CLASSES = ["HUNTER_MISS", "HANDOFF_LOSS", "HALLUCINATION", "NON_CONVERGENCE"]


@dataclass
class ArmScenarioOutcome:
    arm: str  # "1section" | "2section" | "3section" | "council"
    scenario: str
    outcome: str
    detail: str = ""
    grounded_tp: int = 0
    hallucinated: int = 0
    ground_truth: list[str] = field(default_factory=list)


def classify(
    *,
    arm: str,
    scenario: str,
    verdict: str,
    technique_ids: list[str],
    ground_truth: set[str],
    trace: list[dict],
    match_grade: str = "NONE",
    similar_to: list[str] | None = None,
) -> ArmScenarioOutcome:
    """Diagnose one (arm, scenario). Order of tests is the diagnosis priority.

    - HIT: at least one grounded true-positive technique.
    - NOVELTY: ANOMALOUS_UNCLASSIFIED with a grounded SIMILAR neighbour (I8 win).
    - NON_CONVERGENCE: UNRESOLVED (orchestrator budget, never a section verdict).
    - HALLUCINATION: a conclusion whose techniques are entirely absent from GT.
    - HANDOFF_LOSS: trace shows the Hunter surfaced a GT technique but the final
      verdict dropped it (found-but-not-confirmed — the §2.1 failure, now measured).
    - HUNTER_MISS: no GT technique ever appears in the gathered evidence/trace.
    """
    tps = [t for t in technique_ids if t in ground_truth]
    halluc = [t for t in technique_ids if t not in ground_truth]
    similar_to = similar_to or []

    if tps:
        return ArmScenarioOutcome(
            arm,
            scenario,
            "HIT",
            detail=",".join(tps),
            grounded_tp=len(tps),
            hallucinated=len(halluc),
            ground_truth=sorted(ground_truth),
        )
    if (
        verdict == "ANOMALOUS_UNCLASSIFIED"
        and match_grade == "SIMILAR"
        and any(s in ground_truth for s in similar_to)
    ):
        return ArmScenarioOutcome(
            arm, scenario, "NOVELTY", detail=",".join(similar_to), ground_truth=sorted(ground_truth)
        )
    if verdict == "UNRESOLVED":
        return ArmScenarioOutcome(
            arm, scenario, "NON_CONVERGENCE", ground_truth=sorted(ground_truth)
        )

    hunter_saw_gt = _trace_mentions_any(trace, ground_truth)
    if halluc and not tps:
        # A confident wrong answer. If the Hunter had actually surfaced the GT and
        # the final verdict still went elsewhere, that's a handoff loss, not raw
        # hallucination — the distinction the decision rule needs.
        if hunter_saw_gt:
            return ArmScenarioOutcome(
                arm,
                scenario,
                "HANDOFF_LOSS",
                detail=",".join(halluc),
                hallucinated=len(halluc),
                ground_truth=sorted(ground_truth),
            )
        return ArmScenarioOutcome(
            arm,
            scenario,
            "HALLUCINATION",
            detail=",".join(halluc),
            hallucinated=len(halluc),
            ground_truth=sorted(ground_truth),
        )
    if hunter_saw_gt:
        return ArmScenarioOutcome(arm, scenario, "HANDOFF_LOSS", ground_truth=sorted(ground_truth))
    return ArmScenarioOutcome(arm, scenario, "HUNTER_MISS", ground_truth=sorted(ground_truth))


def _extract_evidence_list(raw: str) -> list[str]:
    """Pull a section's cited `evidence` array out of its raw model-response
    text, ignoring `reasoning`/`request_more` prose entirely — those are
    where a model brainstorms candidate techniques ("could involve X, Y, or
    Z") without having found any of them, and treating that prose as "found"
    is exactly the second measurement bug documented in
    `_trace_mentions_any` below."""
    if not raw:
        return []
    depth = 0
    start = None
    blocks = []
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append(raw[start : i + 1])
    for block in reversed(blocks):
        try:
            obj = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict) and ("evidence" in obj or "technique_ids" in obj):
            ev = obj.get("evidence") or []
            return [str(e) for e in ev] if isinstance(ev, list) else []
    return []


def _trace_mentions_any(trace: list[dict], techniques: set[str]) -> bool:
    """Did the Hunter/tool actually surface real, CITED evidence *of these
    specific techniques* — not just mention them as a candidate hypothesis?

    Scope, by trace-entry shape:
    - 1-section (`role == "tool"`): its `content` field is real retrieved
      telemetry, not model prose — matched as-is.
    - 2/3-section/council (`section` in reasoning/expert/merged/council_member/
      arbiter): only that section's own cited `evidence` list, extracted from
      its `raw` response text. Its `reasoning`/`request_more` prose is never
      scanned — see `_extract_evidence_list`.
    - A `section == "tool"` entry's `query` (the retrieval ASK) is never
      scanned either — asking for telemetry isn't evidence that any was found.

    Match itself is KNOWN-MARKER / ID-substring: literal MITRE ID,
    parent-number substring, or a known technique -> Windows Event ID mapping
    (blue.TECHNIQUE_EVENT_ID_MARKERS).

    This function has had two prior, broader (and wrong) versions, both found
    live against the full 89-scenario ablation corpus:

    1. (found 2026-07-19, reverted 2026-07-22) A STRUCTURAL shortcut: any real
       (non-fixture) tool-section retrieval anywhere in the trace, regardless
       of topic, counted as "saw it." Fired on 267/267 (100%) of both
       2-section and 3-section records — e.g. a tool round that only ever
       retrieved generic PowerShell/whoami process-creation events got
       credited as "saw" a Kerberoasting/DCSync ground truth it never queried
       for. Made HUNTER_MISS structurally impossible for those two arms (0.0%
       in both) while 1-section, with no such shortcut available, landed at
       99.6% HUNTER_MISS — three arms scored on three different criteria.
    2. (found 2026-07-22, same day) Even after removing shortcut #1, marker/
       ID-substring matching against the WHOLE trace blob — including
       `reasoning`/`request_more` prose — still let a model's own
       hypothesis-brainstorming count as "found": 59.2% of 3-section's
       "saw it" credit came from a ground-truth ID appearing only in text
       like "could involve techniques like credential dumping (T1003)..." —
       a candidate the model considered and then found no support for, not
       evidence it actually gathered. Only 7.9% of records had grounding tied
       to real evidence content. Fixed by scoping the match to cited
       `evidence` lists / real tool-result content only, per above.

    Ground truth in this harness is always a real classified MITRE ID (never
    a truly-unclassified novel label), so ID/parent-substring text matching
    already generalizes reasonably (20 of 29 corpus ground-truth techniques
    have no event-ID marker at all, but are still catchable via literal
    ID-substring mentions within cited evidence) without either shortcut's
    false-positive cost.
    """
    from portal.modules.security.core.blue import TECHNIQUE_EVENT_ID_MARKERS

    parts: list[str] = []
    for entry in trace or []:
        if entry.get("role") == "tool":
            parts.append(str(entry.get("content", "")))
            continue
        raw = entry.get("raw")
        if raw:
            parts.extend(_extract_evidence_list(raw))

    blob = " ".join(parts).lower()
    for t in techniques:
        t_upper = t.upper()
        if t.lower() in blob:
            return True
        tid_base = t_upper.split(".")[0] if "." in t_upper else t_upper
        tid_number = tid_base[1:] if tid_base.startswith("T") else tid_base
        if tid_number and tid_number in blob:
            return True
        for eid in TECHNIQUE_EVENT_ID_MARKERS.get(t_upper, []):
            if eid in blob:
                return True
    return False


@dataclass
class ArmSummary:
    arm: str
    n: int = 0
    hits: int = 0
    novelty: int = 0
    real_recall: float = 0.0  # (hits + novelty) / n
    miss_hist: dict = field(default_factory=dict)  # MISS_CLASS -> fraction of misses
    hallucination_rate: float = 0.0  # HALLUCINATION / n
    nonconv_rate: float = 0.0  # NON_CONVERGENCE / n


def summarize(arm: str, outcomes: list[ArmScenarioOutcome]) -> ArmSummary:
    n = len(outcomes) or 1
    hits = sum(o.outcome == "HIT" for o in outcomes)
    nov = sum(o.outcome == "NOVELTY" for o in outcomes)
    misses = [o for o in outcomes if o.outcome in MISS_CLASSES]
    m = len(misses) or 1
    hist = {c: round(sum(o.outcome == c for o in misses) / m, 3) for c in MISS_CLASSES}
    return ArmSummary(
        arm=arm,
        n=len(outcomes),
        hits=hits,
        novelty=nov,
        real_recall=round((hits + nov) / n, 3),
        miss_hist=hist,
        hallucination_rate=round(sum(o.outcome == "HALLUCINATION" for o in outcomes) / n, 3),
        nonconv_rate=round(sum(o.outcome == "NON_CONVERGENCE" for o in outcomes) / n, 3),
    )


# Decision-rule thresholds (Phase 3) — tunable knobs, recorded in the report
# whenever decide_route runs.
SPLIT_MARGIN = 0.10
DEGEN_ERR = 0.20
DEGEN_RECALL = 0.05
DOMINANT = 0.40


def decide_route(decision: dict, *, nonconv_progress_frac: float | None = None) -> tuple[str, str]:
    """Convert one ABLATION_DECISION.json into a route. Deterministic, auditable.

    `nonconv_progress_frac` — the fraction of the dominant arm's NON_CONVERGENCE
    cases whose trace shows real progress before budget ran out (as opposed to
    stalling immediately) — is not part of the committed ABLATION_DECISION.json
    schema (it needs per-scenario trace inspection, not just the aggregate
    ArmSummary). Callers with that data pass it explicitly; when omitted, this
    rule assumes progress WAS made (True-ish), i.e. still prefers a cheap
    budget-tune attempt over jumping straight to Council build cost — the
    conservative direction, since under-provisioning rounds is far cheaper to
    fix than building Council on a starved budget it never got to prove itself
    against. Rule order is the diagnosis priority; do not reorder (I10).
    """
    if decision.get("honest_blocked"):
        return "BLOCKED", "degenerate/inconclusive data — re-instrument or re-capture, do not build"

    error_rate = decision.get("error_rate", 0.0)
    if error_rate > DEGEN_ERR:
        return "BLOCKED", "degenerate/inconclusive data — re-instrument or re-capture, do not build"

    arms = decision.get("arms", {})
    all_low = arms and all(a.get("real_recall", 0.0) < DEGEN_RECALL for a in arms.values())
    if all_low:
        max_dominant = max(
            (max(a.get("miss_hist", {}).values(), default=0.0) for a in arms.values()),
            default=0.0,
        )
        if max_dominant < DOMINANT:
            return (
                "BLOCKED",
                "degenerate/inconclusive data — re-instrument or re-capture, do not build",
            )

    best_arm = decision.get("best_multi_arm")
    best = arms.get(best_arm, {})
    misses = best.get("miss_hist", {})
    if not misses:
        return (
            "COUNCIL",
            "models see the evidence but conclude wrongly/inconsistently — cross-check them",
        )
    top_class = max(misses, key=misses.get)
    top_frac = misses[top_class]

    if top_class == "HUNTER_MISS" and top_frac >= DOMINANT:
        return (
            "RETRIEVAL_FIRST",
            "evidence not gathered — council cannot cross-check absent evidence",
        )

    if top_class == "NON_CONVERGENCE" and top_frac >= DOMINANT:
        progressed = True if nonconv_progress_frac is None else nonconv_progress_frac >= 0.5
        if progressed:
            return (
                "BUDGET_FIRST",
                "loop cut off mid-progress — tune rounds before adding council cost",
            )

    return (
        "COUNCIL",
        "models see the evidence but conclude wrongly/inconsistently — cross-check them",
    )
