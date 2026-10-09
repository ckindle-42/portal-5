"""review.pipeline -- one window in, ranked concerns out. The deterministic spine.

    window records --(intake)--> units --(funnel: unusual / known_similar, calibrated)-->
    candidates --(knowledge: nearest anchors, explained)--> outcomes --(optional judge)--> concerns

Everything here is deterministic given the embedder; the judge (``judge``) is an optional
stage injected as a callable, so the deterministic arm is always available as the measured
baseline and as the fallback when no model is reachable.

Outcome table (discovery-first; the library names a concern, it never triggers one):

    similar-flagged, best anchor benign, relation allows suppression -> RECOGNIZED_NORMAL
    similar-flagged, anchor is a confirmed finding / detection, EXACT -> KNOWN_INSTANCE (floor)
    similar-flagged, relation EXACT                                   -> UNKNOWN_SAME
    similar-flagged, otherwise                                        -> COUSIN
    unusual-flagged only                                              -> NOVEL (+ AbsenceReceipt)

Suppression of a benign look-alike is a policy (``ReviewConfig.suppress_benign``), default
``exact_only``: an attacker mimicking a benign pattern is a cousin of it, and silencing
"similar to something benign" would be silencing exactly the product.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..bully import baseline as baseline_mod
from . import CONTRACT_VERSION
from .calibration import CalibrationInsufficient, CalibrationSet
from .contracts import (
    AbsenceReceipt,
    Channel,
    EvidenceRef,
    JudgeRecord,
    Outcome,
    Resemblance,
    ReviewConcern,
    ReviewResult,
    StageReceipt,
)
from .funnel import (
    CHANNEL_SIMILAR,
    CHANNEL_UNUSUAL,
    FunnelDecision,
    FunnelPolicy,
    UnitScores,
    calibrate,
    decide,
    fit_baseline,
    rank,
    split_units,
    unusual_score,
)
from .intake import IntakeResult, IntakeUnit
from .knowledge import AnchorCard, AnchorIndex, Embedder, embed_texts, explain

#: How many evidence refs a concern carries (presentation bound; the total is in the brief).
EVIDENCE_REFS_SHOWN = 200

_FLOOR_KINDS = frozenset({"confirmed_finding", "detection_coverage"})

JudgeFn = Callable[[ReviewConcern, IntakeResult], JudgeRecord]
CancelFn = Callable[[], None]
ProgressFn = Callable[[str, int, int], None]


@dataclass(frozen=True)
class ReviewConfig:
    policy: FunnelPolicy
    suppress_benign: str = "exact_only"  # exact_only | similar_or_exact | never
    top_k_anchors: int = 3
    judge_max: int | None = None  # None: judge every concern (receipted either way)


@dataclass
class Reference:
    """What 'normal' and 'null' mean for an environment: a baseline and the calibrations."""

    baseline: baseline_mod.NormalBaseline
    calibrations: CalibrationSet
    basis: str
    degraded: list[str] = field(default_factory=list)
    calibration_window: IntakeResult | None = None


def _by_level(units: Sequence[IntakeUnit], levels: Sequence[str]) -> dict[str, list[IntakeUnit]]:
    out: dict[str, list[IntakeUnit]] = {lvl: [] for lvl in levels}
    for u in units:
        if u.unit.level in out:
            out[u.unit.level].append(u)
    return out


def build_reference(
    benign: IntakeResult,
    *,
    policy: FunnelPolicy,
    index: AnchorIndex | None,
    embedder: Embedder | None,
    environment_id: str,
    basis: str = "benign_slice",
) -> Reference:
    """Fit the baseline on one half of a benign window and the null distributions on the other.

    Levels with too few held-out benign units to certify ``alpha`` are skipped (and reported):
    a channel that cannot be certified raises nothing rather than guessing."""
    by_unit = {u.unit.unit_id: u for u in benign.units}
    fit_half, cal_half = split_units([u.unit for u in benign.units], salt=environment_id)
    model = fit_baseline(fit_half, environment_id)
    cals = CalibrationSet()
    degraded: list[str] = []
    if basis != "benign_slice":
        degraded.append(f"calibration basis is {basis!r}, not a held-out benign slice")

    cal_units = _by_level([by_unit[u.unit_id] for u in cal_half], policy.levels)
    for level, units in cal_units.items():
        try:
            calibrate(
                CHANNEL_UNUSUAL,
                level,
                [unusual_score(u.unit, model) for u in units],
                policy.alpha_unusual,
                basis=basis,
                into=cals,
            )
        except CalibrationInsufficient as exc:
            degraded.append(f"unusual/{level}: {exc}")
        if index is None or embedder is None or index.population == 0 or not units:
            continue
        sims = _best_similarities(units, index, embedder, exclude_self=True)
        try:
            calibrate(
                CHANNEL_SIMILAR,
                level,
                sims,
                policy.alpha_similar,
                basis=basis,
                embedder_id=index.embedder_id,
                into=cals,
            )
        except CalibrationInsufficient as exc:
            degraded.append(f"known_similar/{level}: {exc}")
    return Reference(model, cals, basis, degraded, benign)


def _best_similarities(
    units: Sequence[IntakeUnit], index: AnchorIndex, embedder: Embedder, *, exclude_self: bool
) -> list[float]:
    queries = embed_texts(embedder, [u.card for u in units])
    exclude = [frozenset({u.unit.unit_id}) for u in units] if exclude_self else None
    hits = index.search(queries, k=1, exclude=exclude)
    return [h[0][1] if h else -1.0 for h in hits]


def _brief(
    outcome: Outcome,
    unit: IntakeUnit,
    resembles: Sequence[Resemblance],
    absence: AbsenceReceipt | None,
    shown: int,
) -> str:
    span = (
        f"{unit.unit.span_seconds:.0f}s" if unit.unit.span_seconds is not None else "unknown span"
    )
    head = (
        f"{outcome.value}: {unit.unit.level} over {len(unit.source_ids)} source(s), "
        f"{len(unit.event_ids)} event(s), {span}"
    )
    if len(unit.event_ids) > shown:
        head += f" (first {shown} cited)"
    if resembles:
        top = resembles[0]
        head += (
            f"; resembles {top.anchor_label} ({top.anchor_kind}, similarity {top.similarity:.2f}, "
            f"p={top.empirical_p:.3g})"
        )
        if top.diverges:
            head += f"; diverges on: {', '.join(top.diverges[:4])}"
    elif absence is not None:
        head += f"; {absence.statement}"
    return head


def _absence(
    index: AnchorIndex | None, best: float | None, cals: CalibrationSet, level: str
) -> AbsenceReceipt:
    cal = cals.get(CHANNEL_SIMILAR, level)
    threshold = cal.threshold if cal else None
    pop = index.population if index else 0
    statement = (
        f"no anchor resembles this above the calibrated threshold "
        f"(searched {pop} anchors; closest similarity "
        f"{'n/a' if best is None else f'{best:.2f}'}, threshold "
        f"{'uncalibrated' if threshold is None else f'{threshold:.2f}'})"
    )
    return AbsenceReceipt(
        population=pop,
        kinds=index.kinds if index else (),
        embedder_id=index.embedder_id if index else "",
        closest_similarity=best,
        threshold=threshold,
        calibration_id=cal.calibration_id if cal else "",
        statement=statement,
    )


def _resemblances(
    unit: IntakeUnit, hits: Sequence[tuple[AnchorCard, float]], cals: CalibrationSet
) -> list[Resemblance]:
    cal = cals.get(CHANNEL_SIMILAR, unit.unit.level)
    out: list[Resemblance] = []
    for card, sim in hits:
        _rel, shares, diverges = explain(unit.unit, card.record)
        out.append(
            Resemblance(
                anchor_id=card.anchor_id,
                anchor_kind=card.kind,
                anchor_label=card.label,
                similarity=sim,
                empirical_p=cal.p_value(sim) if cal else 1.0,
                malice=card.malice,
                shares=shares,
                diverges=diverges,
            )
        )
    return out


def review_window(
    window: IntakeResult,
    *,
    reference: Reference,
    index: AnchorIndex | None,
    embedder: Embedder | None,
    config: ReviewConfig,
    judge: JudgeFn | None = None,
    run_id: str | None = None,
    cancel: CancelFn | None = None,
    progress: ProgressFn | None = None,
) -> ReviewResult:
    started = time.time()
    result = ReviewResult(run_id=run_id or f"rv-{uuid.uuid4().hex[:12]}", fingerprint={})
    result.receipts.extend(window.receipts)
    result.degraded.extend(reference.degraded)
    if window.blind_sources:
        result.degraded.append(f"blind sources (no usable roles): {sorted(window.blind_sources)}")

    levels = config.policy.levels
    scored = [u for u in window.units if u.unit.level in levels]
    similar_hits: list[list[tuple[AnchorCard, float]]] = [[] for _ in scored]
    if index is not None and embedder is not None and index.population and scored:
        if cancel:
            cancel()
        queries = embed_texts(embedder, [u.card for u in scored])
        similar_hits = index.search(queries, k=config.top_k_anchors)

    scores: list[UnitScores] = []
    for i, u in enumerate(scored):
        best = similar_hits[i][0][1] if similar_hits[i] else None
        scores.append(
            UnitScores(
                unit_id=u.unit.unit_id,
                level=u.unit.level,
                unusual=unusual_score(u.unit, reference.baseline),
                similar=best,
                n_sources=len(u.source_ids),
            )
        )
        if progress and i % 500 == 0:
            progress("score", i, len(scored))

    decisions = rank(decide(scores, reference.calibrations, config.policy))
    result.receipts.append(StageReceipt("funnel.scored", len(window.units), len(scores)))
    flagged = [d for d in decisions if d.flagged]
    result.receipts.append(
        StageReceipt(
            "funnel.flagged",
            len(decisions),
            len(flagged),
            note="; ".join(
                sorted({f"uncalibrated {c}" for d in decisions for c in d.uncalibrated})
            ),
        )
    )

    hits_by_unit = {u.unit.unit_id: similar_hits[i] for i, u in enumerate(scored)}
    units_by_id = {u.unit.unit_id: u for u in scored}
    for decision in flagged:
        if cancel:
            cancel()
        concern = _concern_for(
            decision,
            units_by_id[decision.unit_id],
            hits_by_unit[decision.unit_id],
            reference,
            index,
            config,
        )
        if concern.outcome == Outcome.RECOGNIZED_NORMAL:
            result.suppressed.append(concern)
        else:
            result.concerns.append(concern)

    result.receipts.append(
        StageReceipt(
            "outcomes",
            len(flagged),
            len(result.concerns),
            note=f"suppressed as recognized-normal: {len(result.suppressed)}",
        )
    )

    if judge is not None:
        limit = len(result.concerns) if config.judge_max is None else config.judge_max
        judged = 0
        for concern in result.concerns[:limit]:
            if cancel:
                cancel()
            concern.judge = judge(concern, window)
            judged += 1
        result.receipts.append(StageReceipt("judge", len(result.concerns), judged))

    result.fingerprint = {
        "contract": CONTRACT_VERSION,
        "embedder": index.embedder_id if index else "",
        "calibrations": ",".join(reference.calibrations.ids()),
        "baseline_basis": reference.basis,
        "policy": (
            f"alpha_unusual={config.policy.alpha_unusual};alpha_similar={config.policy.alpha_similar};"
            f"levels={','.join(config.policy.levels)};suppress={config.suppress_benign}"
        ),
    }
    result.finished_at = time.time()
    result.started_at = started
    return result


def _concern_for(
    decision: FunnelDecision,
    unit: IntakeUnit,
    hits: Sequence[tuple[AnchorCard, float]],
    reference: Reference,
    index: AnchorIndex | None,
    config: ReviewConfig,
) -> ReviewConcern:
    resembles: list[Resemblance] = []
    absence: AbsenceReceipt | None = None
    if decision.flagged_similar and hits:
        resembles = _resemblances(unit, hits, reference.calibrations)
        top_card = hits[0][0]
        relation, _shares, _diverges = explain(unit.unit, top_card.record)
        if top_card.malice == "benign":
            suppress = config.suppress_benign == "similar_or_exact" or (
                config.suppress_benign == "exact_only" and relation == "EXACT"
            )
            outcome = Outcome.RECOGNIZED_NORMAL if suppress else Outcome.COUSIN
        elif top_card.kind in _FLOOR_KINDS and relation == "EXACT":
            outcome = Outcome.KNOWN_INSTANCE
        elif relation == "EXACT":
            outcome = Outcome.UNKNOWN_SAME
        else:
            outcome = Outcome.COUSIN
    else:
        best = hits[0][1] if hits else None
        absence = _absence(index, best, reference.calibrations, unit.unit.level)
        outcome = Outcome.NOVEL
        if hits:
            resembles = _resemblances(unit, hits[:1], reference.calibrations)

    refs = tuple(
        EvidenceRef(event_id=eid, source_id=eid.rsplit(":", 1)[0])
        for eid in unit.event_ids[:EVIDENCE_REFS_SHOWN]
    )
    channels = tuple(
        Channel.UNUSUAL if c == CHANNEL_UNUSUAL else Channel.KNOWN_SIMILAR
        for c in decision.channels
    )
    return ReviewConcern(
        concern_id=f"cn-{uuid.uuid4().hex[:12]}",
        unit_id=unit.unit.unit_id,
        level=unit.unit.level,
        outcome=outcome,
        channels=channels,
        priority_p=decision.rank_p,
        unusual_p=decision.unusual_p,
        similar_p=decision.similar_p,
        entities=tuple(unit.unit.entities),
        source_ids=unit.source_ids,
        span_seconds=unit.unit.span_seconds,
        evidence=refs,
        resembles=tuple(resembles),
        absence=absence,
        brief=_brief(outcome, unit, resembles, absence, EVIDENCE_REFS_SHOWN),
    )


def anchors_from_units(
    units: Sequence[IntakeUnit],
    *,
    kind: str,
    label: str,
    malice: str,
    prefix: str,
    metadata: Mapping[str, Any] | None = None,
) -> list[Any]:
    """Library ``Anchor`` objects built from already-understood units (an anchor is a unit
    somebody has understood). Knowledge plane: ``label`` is knowledge about the known thing."""
    from ..bully import anchors as anchors_mod
    from .knowledge import record_from_unit

    out: list[Any] = []
    for i, u in enumerate(units):
        record = record_from_unit(u.unit, u.terms, u.card)
        record["label"] = label
        if metadata:
            record.update(dict(metadata))
        out.append(
            anchors_mod.make_anchor(
                kind,
                record,
                source_id=prefix,
                label_basis="analyst_or_source",
                malice=malice,
                anchor_id=f"{prefix}-{i:05d}",
            )
        )
    return out
