"""bully.series_cousin -- cousinhood is decided over a SERIES of logs, not one.

The flaw this corrects runs through the whole design: anchors were single
behavioural signatures and the cousin decision was signature-to-signature. But
a technique in the real world -- and in every `attack_data` dataset -- is not a
single event. It is a SERIES of logs: a process-create, then a network
connection, then a registry write; an auth, then an enumeration, then an
escalation. The known thing is a sequence; the observed thing (an entity's
stitched cross-source timeline, from correlation.py) is a sequence. So "is it a
cousin" must be a comparison of two SEQUENCES, not two points.

This is how it should have been designed from the source event data. A
`BehaviouralSeries` is the ordered behavioural-class spine of a technique
(derived from its logs, vocabulary already lifted to L3 classes by the pyramid
module). Cousinhood is sequence alignment:

  - EXACT    the observed spine matches a known spine (order and classes),
             allowing benign interleaving -- a known technique, robustly.
  - COUSIN   the observed spine ALIGNS to a known spine: same choke-point
             sub-sequence in order, with substitutions/insertions/deletions
             within tolerance. Same behaviour, different realization -- the
             product. A single missing or added step does not break it; a
             different behavioural backbone does.
  - NOVEL/NONE  no known series aligns.

Why alignment, not set overlap: two techniques can share the same *set* of
behaviour classes but be different techniques because the ORDER differs
(enumerate->escalate is privilege abuse; escalate->enumerate after a foothold
is something else). Order is signal. And an attacker's cousin keeps the
backbone order while varying the incidental steps -- exactly what local
sequence alignment (Smith-Waterman-style) scores well and set overlap cannot
see.

The score is normalized by the KNOWN series length so distance is comparable
across techniques of different lengths, and gap/substitution penalties are
weighted by behavioural salience (a shared rare choke-point class closes more
distance than a shared ubiquitous one) -- carried over from the discriminative
weighting the earlier passes established.

Pure compute (COLD). Operates on behavioural-class sequences; never on labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import pyramid

ALGORITHM_VERSION = "series-cousin-v1"

# Alignment scoring. A match on a behavioural choke point is worth most; a
# substitution (one behaviour swapped for another) is a partial break; a gap
# (an inserted/omitted step) is a minor break -- attackers add/skip steps.
MATCH_SCORE = 2.0
SUBSTITUTION_PENALTY = -1.0
GAP_PENALTY = -0.5

# Cousinhood bands on the normalized alignment distance (0 = identical spine,
# 1 = no alignment). Recorded on every decision; a change is a re-baseline.
EXACT_MAX_DISTANCE = 0.15
COUSIN_MAX_DISTANCE = 0.55
# A real technique series has at least this many choke-point steps aligned,
# else a single coincidental shared class would read as a cousin.
MIN_ALIGNED_SPINE = 2


@dataclass(frozen=True)
class BehaviouralSeries:
    """A technique as an ordered series of behavioural classes, derived from
    its logs. `series_id` names the known technique or the observed episode;
    `spine` is the ordered class sequence; `provenance` records how many raw
    logs it came from, so a 1-log 'series' is visibly thin."""

    series_id: str
    spine: tuple[str, ...]
    n_logs: int
    source_ids: tuple[str, ...] = ()
    technique: str | None = None

    @property
    def is_multi_log(self) -> bool:
        return self.n_logs >= 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "spine": list(self.spine),
            "n_logs": self.n_logs,
            "source_ids": list(self.source_ids),
            "technique": self.technique,
            "is_multi_log": self.is_multi_log,
        }


def series_from_logs(
    series_id: str,
    logs: list[dict[str, Any]],
    *,
    action_of: Any,
    classifier: Any = None,
    technique: str | None = None,
    source_ids: tuple[str, ...] = (),
) -> BehaviouralSeries:
    """Build a behavioural series from an ordered list of log records. Each
    log contributes its behavioural class (via the pyramid classifier over its
    action verb); unclassifiable logs contribute nothing to the spine but ARE
    counted in `n_logs` (so a series that is mostly unreadable is visibly
    thin, not silently short). This is the source-event-data-first construction
    the design should have had from the start."""
    spine: list[str] = []
    for log in logs:
        verb = action_of(log)
        cls = pyramid.classify_behavior(verb or "", classifier)
        if cls:
            spine.append(cls)
    return BehaviouralSeries(
        series_id=series_id,
        spine=tuple(spine),
        n_logs=len(logs),
        source_ids=source_ids,
        technique=technique,
    )


def _salience(cls: str, idf: dict[str, float]) -> float:
    return idf.get(cls, 1.0)


def _align(
    observed: tuple[str, ...], known: tuple[str, ...], idf: dict[str, float]
) -> tuple[float, tuple[str, ...]]:
    """Local sequence alignment (Smith-Waterman) of two behavioural spines,
    salience-weighted. Returns (best_score, aligned_spine). The aligned spine
    is the ordered backbone the two share -- the cousin's shared choke points."""
    m, n = len(observed), len(known)
    if m == 0 or n == 0:
        return 0.0, ()
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    back = [[None] * (n + 1) for _ in range(m + 1)]
    best = 0.0
    best_ij = (0, 0)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if observed[i - 1] == known[j - 1]:
                diag = dp[i - 1][j - 1] + MATCH_SCORE * _salience(observed[i - 1], idf)
                move = "match"
            else:
                diag = dp[i - 1][j - 1] + SUBSTITUTION_PENALTY
                move = "sub"
            up = dp[i - 1][j] + GAP_PENALTY
            left = dp[i][j - 1] + GAP_PENALTY
            cell = max(0.0, diag, up, left)
            dp[i][j] = cell
            if cell == 0.0:
                back[i][j] = None
            elif cell == diag:
                back[i][j] = ("diag", move)
            elif cell == up:
                back[i][j] = ("up", None)
            else:
                back[i][j] = ("left", None)
            if cell > best:
                best, best_ij = cell, (i, j)
    # trace back the aligned matched classes
    aligned: list[str] = []
    i, j = best_ij
    while i > 0 and j > 0 and back[i][j] is not None:
        direction, move = back[i][j]
        if direction == "diag":
            if move == "match":
                aligned.append(observed[i - 1])
            i, j = i - 1, j - 1
        elif direction == "up":
            i -= 1
        else:
            j -= 1
    aligned.reverse()
    return best, tuple(aligned)


@dataclass(frozen=True)
class SeriesCousinResult:
    relation: str  # EXACT | COUSIN | NOVEL | NONE
    distance: float  # normalized [0,1]
    aligned_spine: tuple[str, ...]  # the shared ordered choke points
    known_series_id: str | None
    known_technique: str | None
    observed_len: int
    known_len: int
    n_logs_observed: int
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation": self.relation,
            "distance": round(self.distance, 4),
            "aligned_spine": list(self.aligned_spine),
            "known_series_id": self.known_series_id,
            "known_technique": self.known_technique,
            "observed_len": self.observed_len,
            "known_len": self.known_len,
            "n_logs_observed": self.n_logs_observed,
            "evidence": self.evidence,
        }


def build_idf(known_series: list[BehaviouralSeries]) -> dict[str, float]:
    """IDF of behavioural classes across the known series library, so a shared
    rare choke point outweighs a shared ubiquitous one."""
    import math

    df: dict[str, int] = {}
    for s in known_series:
        for cls in set(s.spine):
            df[cls] = df.get(cls, 0) + 1
    total = len(known_series) or 1
    return {cls: math.log((total + 1) / (c + 1)) + 1.0 for cls, c in df.items()}


def decide_cousin(
    observed: BehaviouralSeries,
    known_library: list[BehaviouralSeries],
    *,
    idf: dict[str, float] | None = None,
    exact_max: float = EXACT_MAX_DISTANCE,
    cousin_max: float = COUSIN_MAX_DISTANCE,
    min_aligned_spine: int = MIN_ALIGNED_SPINE,
) -> SeriesCousinResult:
    """Decide cousinhood of an observed series against a library of known
    technique series, by sequence alignment. This is the answer to 'how do you
    decide it is a cousin': not point-to-point, but the best ordered alignment
    of the observed log-series spine to a known technique's log-series spine."""
    idf = idf if idf is not None else build_idf(known_library)
    if not observed.spine:
        return SeriesCousinResult(
            relation="NONE",
            distance=1.0,
            aligned_spine=(),
            known_series_id=None,
            known_technique=None,
            observed_len=0,
            known_len=0,
            n_logs_observed=observed.n_logs,
            evidence={"reason": "observed_series_has_no_behavioural_spine"},
        )

    best: SeriesCousinResult | None = None
    for known in known_library:
        if not known.spine:
            continue
        score, aligned = _align(observed.spine, known.spine, idf)
        # normalize: best possible score is matching the whole known spine at
        # its own salience. distance = 1 - achieved/ideal, clamped.
        ideal = sum(MATCH_SCORE * _salience(c, idf) for c in known.spine)
        dist = max(0.0, min(1.0, 1.0 - (score / ideal))) if ideal > 0 else 1.0
        if best is None or dist < best.distance:
            best = SeriesCousinResult(
                relation="",
                distance=dist,
                aligned_spine=aligned,
                known_series_id=known.series_id,
                known_technique=known.technique,
                observed_len=len(observed.spine),
                known_len=len(known.spine),
                n_logs_observed=observed.n_logs,
                evidence={"score": round(score, 3), "ideal": round(ideal, 3)},
            )

    if best is None:
        return SeriesCousinResult(
            relation="NOVEL",
            distance=1.0,
            aligned_spine=(),
            known_series_id=None,
            known_technique=None,
            observed_len=len(observed.spine),
            known_len=0,
            n_logs_observed=observed.n_logs,
            evidence={"reason": "empty_known_library"},
        )

    # A COUSIN needs a SALIENT aligned backbone, not merely >=N of the most
    # common class. Two shared 'execute' steps (ubiquitous) is not a cousin; two
    # shared 'escalate' steps (rare) is. Gate on the summed salience of the
    # aligned spine, normalized by the ideal, so generic overlaps do not qualify.
    aligned_salience = sum(_salience(c, idf) for c in best.aligned_spine)
    known_salience = sum(
        _salience(c, idf)
        for c in (next((k.spine for k in known_library if k.series_id == best.known_series_id), ()))
    )
    salience_fraction = (aligned_salience / known_salience) if known_salience > 0 else 0.0
    distinct_aligned = len(set(best.aligned_spine))
    aligned_ok = (
        len(best.aligned_spine) >= min_aligned_spine
        and distinct_aligned >= 2  # a real backbone, not one verb repeated
        and salience_fraction >= 0.4
    )

    # EXACT additionally requires the observed series to be nearly the same
    # LENGTH as the known one -- an inserted or omitted step makes it a COUSIN,
    # not the exact technique. Length divergence a point-comparison cannot see.
    len_div = abs(best.observed_len - best.known_len) / max(best.observed_len, best.known_len, 1)

    if best.distance <= exact_max and aligned_ok and len_div <= 0.15:
        relation = "EXACT"
    elif best.distance <= cousin_max and aligned_ok:
        relation = "COUSIN"
    elif best.distance >= 0.99 or not aligned_ok:
        # aligns to nothing salient: NOVEL if the observed spine is itself
        # substantial (real behaviour we simply do not know), else NONE.
        relation = (
            "NOVEL"
            if (observed.is_multi_log and len(observed.spine) >= min_aligned_spine)
            else "NONE"
        )
    else:
        relation = "NONE"

    return SeriesCousinResult(
        relation=relation,
        distance=best.distance,
        aligned_spine=best.aligned_spine,
        known_series_id=best.known_series_id if relation in ("EXACT", "COUSIN") else None,
        known_technique=best.known_technique if relation in ("EXACT", "COUSIN") else None,
        observed_len=best.observed_len,
        known_len=best.known_len,
        n_logs_observed=best.n_logs_observed,
        evidence=best.evidence,
    )
