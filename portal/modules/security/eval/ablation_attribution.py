"""Failure-attribution for blue-orchestration ablation runs.

Turns one (arm, scenario) OrchestrationResult + its scoring into a single
diagnosis class, so the corpus aggregate can ROUTE the next build (retrieval
vs budget vs council) instead of guessing. Hermetic: operates on plain dicts
(trace + scoring + ground truth), no live calls. Proven on fixtures (I9).
"""

from __future__ import annotations

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


def _trace_mentions_any(trace: list[dict], techniques: set[str]) -> bool:
    """Did any GT technique appear anywhere the Hunter/tool actually surfaced?
    Executor: match against trace entries' evidence/technique fields; keep it
    conservative (a GT id string present in a trace round's surfaced content)."""
    blob = " ".join(str(entry) for entry in (trace or []))
    return any(t in blob for t in techniques)


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
