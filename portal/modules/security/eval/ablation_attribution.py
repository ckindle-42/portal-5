"""Failure attribution for blue-orchestration ablation runs.

The primary outcome is retained for compact reporting, but causal routing is
not inferred from that label alone.  Every record also carries independent
completion, retrieval-observation, and Hunter-citation states plus secondary
failures.  This prevents branch order from pretending that co-occurring
failures are mutually exclusive.

Hermetic: operates on persisted plain dicts and makes no live calls.  Fixture
coverage establishes implementation behaviour only; it is not evidence that
the instrument is valid on live traces.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

ATTRIBUTION_SCHEMA_VERSION = 2

# Primary outcome of one (arm, scenario).  ATTENTION_LOSS separates "telemetry
# was retrieved but the Hunter did not cite it" from retrieval failure.
# ATTRIBUTION_UNKNOWN is mandatory for legacy/live traces that do not persist
# the retrieved payload; absence from such a trace is not evidence of absence.
OUTCOMES = [
    "HIT",
    "NOVELTY",
    "HUNTER_MISS",
    "ATTENTION_LOSS",
    "HANDOFF_LOSS",
    "HALLUCINATION",
    "NON_CONVERGENCE",
    "ATTRIBUTION_UNKNOWN",
]

MISS_CLASSES = [
    "HUNTER_MISS",
    "ATTENTION_LOSS",
    "HANDOFF_LOSS",
    "HALLUCINATION",
    "NON_CONVERGENCE",
    "ATTRIBUTION_UNKNOWN",
]

RETRIEVAL_SUPPORT = "GT_SUPPORT_MARKER_OBSERVED"
RETRIEVAL_NO_SUPPORT = "NO_GT_SUPPORT_MARKER_OBSERVED"
RETRIEVAL_UNOBSERVABLE = "UNOBSERVABLE"
CITATION_SUPPORT = "GT_SUPPORT_MARKER_CITED"
CITATION_NO_SUPPORT = "NO_GT_SUPPORT_MARKER_CITED"
CITATION_UNOBSERVABLE = "UNOBSERVABLE"


@dataclass
class ArmScenarioOutcome:
    arm: str  # "1section" | "2section" | "3section" | "council"
    scenario: str
    outcome: str
    detail: str = ""
    grounded_tp: int = 0
    hallucinated: int = 0
    ground_truth: list[str] = field(default_factory=list)
    completion_state: str = "CONCLUDED"
    retrieval_state: str = RETRIEVAL_UNOBSERVABLE
    citation_state: str = CITATION_UNOBSERVABLE
    secondary_failures: list[str] = field(default_factory=list)
    attribution_sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceObservation:
    retrieval_state: str
    citation_state: str
    sources: tuple[str, ...] = ()


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
    grounding_verified: bool = True,
) -> ArmScenarioOutcome:
    """Diagnose one (arm, scenario), retaining co-occurring failure axes.

    - HIT: at least one grounded true-positive technique.
    - NOVELTY: ANOMALOUS_UNCLASSIFIED with a grounded SIMILAR neighbour (I8 win).
    - NON_CONVERGENCE: UNRESOLVED (orchestrator budget, never a section verdict).
    - HUNTER_MISS: captured tool payload has no GT-support marker.
    - ATTENTION_LOSS: tool payload has a GT marker but the Hunter did not cite it.
    - HANDOFF_LOSS: both retrieval and Hunter citation carry a GT marker, but
      the final verdict drops it.
    - ATTRIBUTION_UNKNOWN: the trace did not preserve enough tool payload to
      distinguish the preceding stages.

    HALLUCINATION is retained as a secondary failure whenever wrong techniques
    are named.  It is primary only when no earlier-stage causal attribution is
    available.  This avoids hiding retrieval failure merely because the same
    record also contains a confident wrong conclusion.
    """
    tps = [t for t in technique_ids if t in ground_truth]
    halluc = [t for t in technique_ids if t not in ground_truth]
    similar_to = similar_to or []
    observation = _trace_evidence_observation(trace, ground_truth)
    common = {
        "ground_truth": sorted(ground_truth),
        "completion_state": "UNRESOLVED" if verdict == "UNRESOLVED" else "CONCLUDED",
        "retrieval_state": observation.retrieval_state,
        "citation_state": observation.citation_state,
        "attribution_sources": list(observation.sources),
    }

    if verdict == "CONFIRMED" and tps and grounding_verified:
        return ArmScenarioOutcome(
            arm,
            scenario,
            "HIT",
            detail=",".join(tps),
            grounded_tp=len(tps),
            hallucinated=len(halluc),
            secondary_failures=["HALLUCINATION"] if halluc else [],
            **common,
        )
    if (
        verdict == "ANOMALOUS_UNCLASSIFIED"
        and match_grade == "SIMILAR"
        and any(s in ground_truth for s in similar_to)
    ):
        return ArmScenarioOutcome(arm, scenario, "NOVELTY", detail=",".join(similar_to), **common)
    if tps:
        return ArmScenarioOutcome(
            arm,
            scenario,
            "ATTRIBUTION_UNKNOWN",
            detail=",".join(tps),
            hallucinated=len(halluc),
            secondary_failures=[
                "UNVERIFIED_GROUNDING",
                *(["HALLUCINATION"] if halluc else []),
            ],
            **common,
        )
    if verdict == "UNRESOLVED":
        secondary = []
        if observation.retrieval_state == RETRIEVAL_NO_SUPPORT:
            secondary.append("HUNTER_MISS")
        elif observation.retrieval_state == RETRIEVAL_UNOBSERVABLE:
            secondary.append("ATTRIBUTION_UNKNOWN")
        return ArmScenarioOutcome(
            arm, scenario, "NON_CONVERGENCE", secondary_failures=secondary, **common
        )

    secondary = ["HALLUCINATION"] if halluc else []
    if observation.retrieval_state == RETRIEVAL_UNOBSERVABLE:
        return ArmScenarioOutcome(
            arm,
            scenario,
            "ATTRIBUTION_UNKNOWN",
            detail=",".join(halluc),
            hallucinated=len(halluc),
            secondary_failures=secondary,
            **common,
        )
    if observation.retrieval_state == RETRIEVAL_NO_SUPPORT:
        return ArmScenarioOutcome(
            arm,
            scenario,
            "HUNTER_MISS",
            detail=",".join(halluc),
            hallucinated=len(halluc),
            secondary_failures=secondary,
            **common,
        )
    if arm == "1section" and halluc:
        return ArmScenarioOutcome(
            arm,
            scenario,
            "HALLUCINATION",
            detail=",".join(halluc),
            hallucinated=len(halluc),
            **common,
        )
    if observation.citation_state == CITATION_SUPPORT:
        return ArmScenarioOutcome(
            arm,
            scenario,
            "HANDOFF_LOSS",
            detail=",".join(halluc),
            hallucinated=len(halluc),
            secondary_failures=secondary,
            **common,
        )
    return ArmScenarioOutcome(
        arm,
        scenario,
        "ATTENTION_LOSS",
        detail=",".join(halluc),
        hallucinated=len(halluc),
        secondary_failures=secondary,
        **common,
    )


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
    in_string = False
    escaped = False
    for i, ch in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
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


def _text_mentions_any(text: str, techniques: set[str]) -> bool:
    """Conservative marker matching with token boundaries.

    Bare numeric substrings are deliberately forbidden: a ground-truth parent
    number such as ``1003`` can occur in timestamps, ports, counts, or unrelated
    identifiers.  Raw telemetry normally carries event IDs rather than MITRE
    IDs, so known event markers remain supported with numeric boundaries.
    """
    from portal.modules.security.core.blue import TECHNIQUE_EVENT_ID_MARKERS

    blob = text.upper()
    for technique in techniques:
        tid = technique.strip().upper()
        if not tid:
            continue
        base = tid.split(".", 1)[0]
        if re.search(rf"(?<![A-Z0-9]){re.escape(tid)}(?![A-Z0-9.])", blob):
            return True
        if base != tid and re.search(rf"(?<![A-Z0-9]){re.escape(base)}(?![A-Z0-9.])", blob):
            return True
        for event_id in TECHNIQUE_EVENT_ID_MARKERS.get(tid, []):
            # A bare number is not an event marker.  Requiring an EventID /
            # EventCode / Id field prevents common values (especially Sysmon
            # event 10) from firing on ports, timestamps, counts, or addresses.
            event_pattern = (
                rf"(?:EVENT(?:\s*ID|ID|CODE)|\bID)\s*[:=]?\s*"
                rf"{re.escape(str(event_id))}(?!\d)"
            )
            if re.search(event_pattern, blob):
                return True
    return False


def _trace_evidence_observation(trace: list[dict], techniques: set[str]) -> EvidenceObservation:
    """Observe retrieval and Hunter citation separately.

    Only persisted tool payload is evidence of retrieval.  Model-authored
    evidence arrays are evidence that a Hunter *cited* something; they are not
    treated as proof that retrieval returned it.  A real-retrieval trace that
    stores only provenance/query is UNOBSERVABLE and must not be rescored into
    a causal build decision.
    """
    tool_entries: list[dict] = []
    tool_payloads: list[str] = []
    hunter_citations: list[str] = []
    hunter_sections_seen = False
    sources: set[str] = set()

    for entry in trace or []:
        is_tool = entry.get("role") == "tool" or entry.get("section") == "tool"
        if is_tool:
            tool_entries.append(entry)
            payload = entry.get("content")
            if payload is None:
                payload = entry.get("raw_summary")
            if payload:
                tool_payloads.append(str(payload))
                sources.add("tool_content")
            continue
        if entry.get("section") in {"reasoning", "merged"}:
            hunter_sections_seen = True
            evidence = _extract_evidence_list(str(entry.get("raw") or ""))
            if evidence:
                hunter_citations.extend(evidence)
                sources.add("hunter_citation")

    if tool_payloads:
        retrieval_state = (
            RETRIEVAL_SUPPORT
            if _text_mentions_any(" ".join(tool_payloads), techniques)
            else RETRIEVAL_NO_SUPPORT
        )
    elif tool_entries and all(
        entry.get("provenance") in {"empty", "synthetic-fallback"} for entry in tool_entries
    ):
        retrieval_state = RETRIEVAL_NO_SUPPORT
        sources.add("explicit_empty_retrieval")
    else:
        retrieval_state = RETRIEVAL_UNOBSERVABLE

    if hunter_citations:
        citation_state = (
            CITATION_SUPPORT
            if _text_mentions_any(" ".join(hunter_citations), techniques)
            else CITATION_NO_SUPPORT
        )
    elif hunter_sections_seen:
        citation_state = CITATION_NO_SUPPORT
    else:
        citation_state = CITATION_UNOBSERVABLE

    return EvidenceObservation(retrieval_state, citation_state, tuple(sorted(sources)))


def _trace_mentions_any(trace: list[dict], techniques: set[str]) -> bool:
    """Compatibility helper: true only for a GT marker in captured tool data."""
    return _trace_evidence_observation(trace, techniques).retrieval_state == RETRIEVAL_SUPPORT


@dataclass
class ArmSummary:
    arm: str
    n: int = 0
    hits: int = 0
    novelty: int = 0
    real_recall: float = 0.0  # (hits + novelty) / n
    miss_hist: dict = field(default_factory=dict)  # MISS_CLASS -> fraction of misses
    miss_counts: dict = field(default_factory=dict)
    miss_n: int = 0
    scenario_miss_counts: dict = field(default_factory=dict)
    scenario_miss_n: int = 0
    hallucination_rate: float = 0.0  # HALLUCINATION / n
    nonconv_rate: float = 0.0  # NON_CONVERGENCE / n
    false_positive_rate: float = 0.0
    attribution_unknown_rate: float = 0.0
    retrieval_state_hist: dict = field(default_factory=dict)
    secondary_failure_hist: dict = field(default_factory=dict)


def summarize(arm: str, outcomes: list[ArmScenarioOutcome]) -> ArmSummary:
    n_raw = len(outcomes)
    n = n_raw or 1
    hits = sum(o.outcome == "HIT" for o in outcomes)
    nov = sum(o.outcome == "NOVELTY" for o in outcomes)
    misses = [o for o in outcomes if o.outcome in MISS_CLASSES]
    m = len(misses) or 1
    counts = {c: sum(o.outcome == c for o in misses) for c in MISS_CLASSES}
    hist = {c: round(counts[c] / m, 3) for c in MISS_CLASSES}
    by_scenario: dict[str, Counter] = defaultdict(Counter)
    for outcome in misses:
        by_scenario[outcome.scenario][outcome.outcome] += 1
    scenario_counts = dict.fromkeys(MISS_CLASSES, 0)
    for outcome_counts in by_scenario.values():
        ordered = outcome_counts.most_common()
        if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
            scenario_counts["ATTRIBUTION_UNKNOWN"] += 1
        else:
            scenario_counts[ordered[0][0]] += 1
    retrieval_counts = Counter(o.retrieval_state for o in outcomes)
    secondary_counts = Counter(f for o in outcomes for f in o.secondary_failures)
    return ArmSummary(
        arm=arm,
        n=n_raw,
        hits=hits,
        novelty=nov,
        real_recall=round((hits + nov) / n, 3),
        miss_hist=hist,
        miss_counts=counts,
        miss_n=len(misses),
        scenario_miss_counts=scenario_counts,
        scenario_miss_n=len(by_scenario),
        hallucination_rate=round(sum(o.outcome == "HALLUCINATION" for o in outcomes) / n, 3),
        nonconv_rate=round(sum(o.outcome == "NON_CONVERGENCE" for o in outcomes) / n, 3),
        false_positive_rate=round(sum(o.hallucinated > 0 for o in outcomes) / n, 3),
        attribution_unknown_rate=round(
            sum(o.retrieval_state == RETRIEVAL_UNOBSERVABLE for o in outcomes) / n, 3
        ),
        retrieval_state_hist={
            state: round(retrieval_counts.get(state, 0) / n, 3)
            for state in (RETRIEVAL_SUPPORT, RETRIEVAL_NO_SUPPORT, RETRIEVAL_UNOBSERVABLE)
        },
        secondary_failure_hist={
            failure: round(count / n, 3) for failure, count in sorted(secondary_counts.items())
        },
    )


# Decision-rule thresholds (Phase 3) — tunable knobs, recorded in the report
# whenever decide_route runs.
SPLIT_MARGIN = 0.10
DEGEN_ERR = 0.20
DEGEN_RECALL = 0.05
DOMINANT = 0.40
DOMINANT_MARGIN = 0.10
MAX_ATTRIBUTION_UNKNOWN = 0.05
MIN_LIVE_AUDIT_N = 30
MIN_ORACLE_AUDIT_N = 20


def _instrument_validation_error(decision: dict) -> str | None:
    validation = decision.get("instrument_validation") or {}
    if validation.get("schema_version") != ATTRIBUTION_SCHEMA_VERSION:
        return "attribution schema is unvalidated or stale"
    if validation.get("scorer_frozen") is not True:
        return "scorer was not frozen before confirmation"
    if not validation.get("scorer_hash"):
        return "frozen scorer hash is missing"
    live_audit = validation.get("live_audit") or {}
    if live_audit.get("status") != "PASS" or int(live_audit.get("n", 0)) < MIN_LIVE_AUDIT_N:
        return f"blinded live audit has not passed at n>={MIN_LIVE_AUDIT_N}"
    if float(live_audit.get("agreement", 0.0)) < 0.80:
        return "blinded live-audit agreement is below 0.80"
    confirmatory = validation.get("confirmatory") or {}
    if confirmatory.get("status") != "PASS" or confirmatory.get("independent") is not True:
        return "independent confirmatory corpus has not passed"
    development_corpus_id = validation.get("development_corpus_id")
    confirmatory_corpus_id = confirmatory.get("corpus_id")
    if (
        not development_corpus_id
        or not confirmatory_corpus_id
        or development_corpus_id == confirmatory_corpus_id
    ):
        return "development and confirmatory corpus identities are missing or not independent"
    oracle = validation.get("oracle_evidence") or {}
    if oracle.get("status") != "PASS" or int(oracle.get("n", 0)) < MIN_ORACLE_AUDIT_N:
        return "oracle-evidence intervention has not validated the causal route"
    return None


def _wilson_lower(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = successes / total
    z2 = z * z
    centre = p + z2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total)
    return (centre - spread) / (1 + z2 / total)


def _stable_dominant(
    counts: dict[str, int], classes: set[str]
) -> tuple[bool, float, float, str | None]:
    total = sum(int(v) for v in counts.values())
    selected = sum(int(counts.get(c, 0)) for c in classes)
    if total <= 0:
        return False, 0.0, 0.0, "no classified misses"
    fraction = selected / total
    lower = _wilson_lower(selected, total)
    runner = max(
        (int(v) / total for key, v in counts.items() if key not in classes),
        default=0.0,
    )
    stable = (
        fraction >= DOMINANT + DOMINANT_MARGIN
        and lower >= DOMINANT
        and fraction - runner >= DOMINANT_MARGIN
    )
    reason = (
        None
        if stable
        else (
            f"dominance is unstable (point={fraction:.3f}, 95% lower={lower:.3f}, "
            f"runner={runner:.3f})"
        )
    )
    return stable, fraction, lower, reason


def decide_route(decision: dict, *, nonconv_progress_frac: float | None = None) -> tuple[str, str]:
    """Convert one validated decision artifact into a build route.

    Missing validation, unobservable attribution, or threshold instability
    yields INDETERMINATE.  No build direction is used as a default.  Missing
    NON_CONVERGENCE progress is likewise unknown rather than imputed as true.
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

    validation_error = _instrument_validation_error(decision)
    if validation_error:
        return "INDETERMINATE", validation_error

    best_arm = decision.get("best_multi_arm")
    best = arms.get(best_arm, {})
    if best.get("attribution_unknown_rate", 1.0) > MAX_ATTRIBUTION_UNKNOWN:
        return (
            "INDETERMINATE",
            "too much retrieval evidence is unobservable for causal routing",
        )
    counts = best.get("scenario_miss_counts") or {}
    if not counts:
        return "INDETERMINATE", "decision artifact lacks scenario-clustered miss counts"

    stable, _, _, _ = _stable_dominant(counts, {"HUNTER_MISS"})
    if stable:
        oracle = decision["instrument_validation"]["oracle_evidence"]
        if oracle.get("retrieval_mediated") is not True:
            return (
                "INDETERMINATE",
                "retrieval misses dominate observationally, but oracle evidence did not establish retrieval mediation",
            )
        return (
            "RETRIEVAL_FIRST",
            "captured tool payload repeatedly lacks GT-support markers; oracle audit confirms retrieval mediation",
        )

    stable, _, _, _ = _stable_dominant(counts, {"NON_CONVERGENCE"})
    if stable:
        if nonconv_progress_frac is None:
            return "INDETERMINATE", "NON_CONVERGENCE progress was not measured"
        if nonconv_progress_frac >= 0.5:
            return (
                "BUDGET_FIRST",
                "loop cut off mid-progress — tune rounds before adding council cost",
            )
        return "INDETERMINATE", "NON_CONVERGENCE dominates but traces do not show progress"

    stable, _, _, _ = _stable_dominant(counts, {"ATTENTION_LOSS"})
    if stable:
        return (
            "HUNTER_FIRST",
            "GT-support markers were retrieved but not cited by the Hunter",
        )

    stable, _, _, instability = _stable_dominant(counts, {"HANDOFF_LOSS", "HALLUCINATION"})
    if stable:
        return (
            "COUNCIL",
            "validated downstream conclusion failures dominate after retrieval and Hunter citation",
        )

    return "INDETERMINATE", instability or "no validated failure mode dominates stably"
