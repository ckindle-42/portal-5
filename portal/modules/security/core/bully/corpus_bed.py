"""bully.corpus_bed -- bind the hunt to the REAL corpus, and inject cousins of
what the answer key says is already in it.

The gap this closes is the largest one in the project, and it is a wiring gap,
not a missing capability. `portal_wiki/canonical/unit-corpus-injection-*`
documents a fully-implemented three-lane test bed:

    Lane A  BOTS v1/v2/v3      indexes botsv1/botsv2/botsv3   published answer keys
    Lane B  ATT&CK corpora     index portal5_lab              technique-tagged
    Lane C  Caldera / ART      index portal5_lab              UNLABELLED (novelty)

`scripts/lab_bots_install.py` installs Lane A as pre-indexed Splunk buckets --
**millions of real, verifiable, multi-source events with published answers**.
Every bully run to date (R.6, W.6, X.6, Y.6, D.4) instead read
`index=portal5_lab` with `--capture-limit 2000` and got back only the `gen:*`
synthetic universe it had just written itself. BOTS lives under a DIFFERENT
index name, so the capture path could never see it. `inject_plane.
capture_records` even says so in a comment -- "this index also carries a large
pre-loaded historical corpus (millions of events across many sourcetypes)" --
while hardcoding one index and a 2,000-row cap.

Consequence: the generator has been manufacturing BOTH the haystack and the
needles, and the system was measured against data it authored. The signature of
that is in D.4's own numbers -- 2,212 resolved entities from 2,000 records, ~1.1
entities per record -- because each procedurally-invented source invents its own
identifier space, so there is almost nothing to resolve ACROSS sources. Cross-
source entity correlation was being validated on data engineered to have no
cross-source entities.

The wiki also states the design intent this module implements, and states it
better than any run has:

    "Lanes A and B are finite and pre-labeled: every event already carries its
     answer, which makes them ideal for detection coverage and hunt training but
     USELESS FOR DISCOVERY WORK. Lane C is the only lane that generates
     genuinely novel, unlabeled activity, which is what ANOMALOUS_UNCLASSIFIED /
     discovery evaluation needs."

So the test bed is: **BOTS is the haystack** -- real, messy, multi-source, at
scale, with an answer key telling us what is genuinely in it. **The generator's
job is to build COUSINS of techniques the answer key confirms are present, and
inject them into that haystack.** Then the measurement is honest:

    known-bad recall against the published answer key   -> the FLOOR
    injected-cousin recall inside millions of real events -> the PRODUCT
    false-positive rate against real benign traffic      -> the COST

`answer_key_visibility: scorer_only` is already declared in
`config/security_corpus.yaml`; this module honours it -- the answer key reaches
scoring, never the grader (Q3).

Pure compute plus an injected connector factory (COLD): no grading, no model
calls. Volume handling is the caller's; this module never loads a corpus into
memory whole.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "corpus-bed-v1"

# Lane A indexes, as installed by scripts/lab_bots_install.py.
BOTS_INDEXES: tuple[str, ...] = ("botsv1", "botsv2", "botsv3")

# Lane B / live lane.
CORPUS_INDEX = "portal5_lab"

# A haystack must actually be a haystack. Below this the run is not a needle
# search, it is a sample, and its false-positive and rarity numbers do not
# generalise -- D.4 graded 25 units drawn from 2,212 entities (1.1%) and every
# unit scored remarkable because the baseline was fitted on the same 25.
MIN_HAYSTACK_RECORDS = 100_000

# The baseline must be fitted on a population large enough for "rare" to mean
# something. Fit wide, score narrow.
MIN_BASELINE_UNITS = 2_000

# The scored sample itself must be large enough that its recall/FP figures
# generalise. C.6 scored 200 units and published rates as if they did (T.2,
# TASK_BULLY_REAL_TELEMETRY_V1) -- this floor was specified in
# TASK_BULLY_CORPUS_BED_V1 and never landed in this module, so it never ran.
MIN_SCORED_UNITS = 10_000

# The fitted population must be a multiple of the scored population -- "fit
# wide, score narrow" is not satisfied by fitting and scoring the same-sized
# sample, which is what made D.4's discovery_rate degenerate.
MIN_FIT_TO_SCORE_RATIO = 2.0


@dataclass(frozen=True)
class CorpusLane:
    lane: str  # A | B | C
    index: str
    labeled: bool
    answer_key: bool
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "index": self.index,
            "labeled": self.labeled,
            "answer_key": self.answer_key,
            "purpose": self.purpose,
        }


LANES: tuple[CorpusLane, ...] = (
    CorpusLane("A", "botsv1", True, True, "real haystack + published answers"),
    CorpusLane("A", "botsv2", True, True, "real haystack + published answers"),
    CorpusLane("A", "botsv3", True, True, "real haystack + published answers"),
    CorpusLane("B", CORPUS_INDEX, True, False, "technique-tagged corpora + injected cousins"),
    CorpusLane("C", CORPUS_INDEX, False, False, "unlabelled novelty (discovery)"),
)


@dataclass(frozen=True)
class BedReport:
    """Whether the run is actually standing on a haystack. Published so a
    sample can never again be mistaken for a corpus."""

    indexes_queried: tuple[str, ...]
    records_available: dict[str, int]
    records_read: int
    lanes_present: tuple[str, ...]
    is_haystack: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "indexes_queried": list(self.indexes_queried),
            "records_available": dict(self.records_available),
            "records_read": self.records_read,
            "lanes_present": list(self.lanes_present),
            "is_haystack": self.is_haystack,
            "reasons": list(self.reasons),
        }


def resolve_indexes(*, include_bots: bool = True, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Every index the hunt should read. `LAB_SPLUNK_INDEX` remains honoured
    for the live lane, but it is no longer the ONLY index -- that single
    hardcoded binding is why millions of real events were invisible."""
    live = os.environ.get("LAB_SPLUNK_INDEX", CORPUS_INDEX)
    out: list[str] = [live]
    if include_bots:
        out.extend(BOTS_INDEXES)
    out.extend(extra)
    seen: set[str] = set()
    return tuple(i for i in out if not (i in seen or seen.add(i)))


def assess_bed(
    records_available: dict[str, int],
    records_read: int,
    *,
    units_fitted: int,
    units_scored: int,
    min_records: int = MIN_HAYSTACK_RECORDS,
    min_scored_units: int = MIN_SCORED_UNITS,
    min_fit_to_score_ratio: float = MIN_FIT_TO_SCORE_RATIO,
) -> BedReport:
    """Is this a haystack or a sample? A run that cannot answer yes must say
    so in its own output rather than publishing rates computed on a sample.

    `units_fitted`/`units_scored` are required, not optional (T4,
    TASK_BULLY_REAL_TELEMETRY_V1): `MIN_SCORED_UNITS`/`MIN_FIT_TO_SCORE_RATIO`
    were specified in TASK_BULLY_CORPUS_BED_V1 but never wired into this
    function, so C.6 scored 200 units against what should have been a
    10,000-unit floor and the floor never ran. An optional guard input is a
    guard that silently does not run; a required one forces a `TypeError` on
    every caller that omits it, not a silent pass.
    """
    reasons: list[str] = []
    lanes = tuple(sorted({lane.lane for lane in LANES if records_available.get(lane.index, 0) > 0}))
    total = sum(records_available.values())
    is_haystack = True

    # A run that read NOTHING cannot be a haystack, regardless of what the
    # corpus contains. Checked FIRST and unconditionally: `records_read and
    # total and ...` below is skipped when `records_read == 0` (falsy in
    # Python), which is exactly how C.6 published `is_haystack: true` on a
    # run that read zero records (a permanent regression, pinned by test).
    if records_read == 0:
        is_haystack = False
        reasons.append(
            "no_records_read: records_read=0 -- a run that reported reading "
            "nothing cannot be a haystack, no matter how large the corpus is"
        )

    if total < min_records:
        is_haystack = False
        reasons.append(
            f"corpus_too_small:{total}<{min_records} -- this is a sample, not a haystack; "
            "rarity and false-positive rates computed here do not generalise"
        )
    if "A" not in lanes:
        is_haystack = False
        reasons.append(
            "lane_A_absent: no botsv1/2/3 records visible -- the real, answer-keyed "
            "haystack is not installed or not being queried"
        )
    if records_read and total and records_read < total * 0.5:
        reasons.append(
            f"partial_read:{records_read}/{total} -- a capped read of a real corpus "
            "biases every downstream statistic toward whatever the cap selected"
        )
    if units_scored < min_scored_units:
        # A5, TASK_BULLY_ADAPTIVE_REACH_V1: this used to be advisory-only, so
        # I.6 published `is_haystack: true` alongside ZERO scored units
        # (`scored_sample_too_small: 0<10000`) -- a run with no scored
        # population at all cannot claim to be standing on a haystack, no
        # matter how large the corpus behind it is.
        is_haystack = False
        reasons.append(
            f"scored_sample_too_small:{units_scored}<{min_scored_units} -- recall/FP "
            "figures computed on this scored population do not generalise"
        )
    if units_scored and units_fitted < units_scored * min_fit_to_score_ratio:
        reasons.append(
            f"fit_to_score_ratio_too_small:{units_fitted}<{units_scored}*{min_fit_to_score_ratio} "
            "-- 'fit wide, score narrow' is not satisfied by a baseline fitted on a "
            "population no larger than what it scores"
        )
    return BedReport(
        indexes_queried=tuple(sorted(records_available)),
        records_available=dict(records_available),
        records_read=records_read,
        lanes_present=lanes,
        is_haystack=is_haystack,
        reasons=tuple(reasons),
    )


# ── cousins of what the answer key says is present ─────────────────────────


@dataclass(frozen=True)
class AnswerKeyEntry:
    """A technique the published answer key confirms is present in the real
    corpus. Scorer-plane only (`answer_key_visibility: scorer_only`)."""

    dataset: str  # botsv1 | botsv2 | botsv3 | corpus:<src>
    technique: str  # ATT&CK id
    behavioural_spine: tuple[str, ...]
    entities: tuple[str, ...] = ()
    sourcetypes: tuple[str, ...] = ()
    # When known, the real epoch this technique was confirmed active at --
    # used only to place an injected cousin ADJACENT to real activity (I5),
    # never to grade discovery.
    confirmed_at: float | None = None
    # hop distance (from `entities[0]`, via a real live-discovered pivot
    # chain) -> a real entity that many pivots away (A4,
    # TASK_BULLY_ADAPTIVE_REACH_V1). Populated by a live run from an actual
    # investigation over the real corpus, never fabricated. `plan_cousins`
    # plants one cousin PER KNOWN DISTANCE so recovery measures REACH, not
    # planting position: I.6 shipped every cousin under the parent's own
    # entity (0 hops), so `20/20` recovery measured the anchor confirming
    # its own existence, not a pivot.
    entities_by_distance: dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "technique": self.technique,
            "behavioural_spine": list(self.behavioural_spine),
            "entities": list(self.entities),
            "sourcetypes": list(self.sourcetypes),
            "confirmed_at": self.confirmed_at,
            "entities_by_distance": dict(self.entities_by_distance),
        }


@dataclass(frozen=True)
class CousinSpec:
    """A cousin OF A CONFIRMED-PRESENT technique, to be injected into the real
    haystack. This is the thing the product exists to find: same behavioural
    spine, different vocabulary/identity/schema, sitting inside millions of
    real records rather than inside data we authored.

    `injected_at` is always inside the corpus's own time range (I5) -- a
    cousin shipped with a "now" timestamp sits years away from the haystack
    it was meant to hide in, and no time-bounded investigation can ever
    reach it (the T.3 defect this closes). `anchor_entity` carries a real
    entity from the parent technique so the cousin is reachable by a pivot,
    not merely present at the right time.
    """

    cousin_id: str
    parent_technique: str
    parent_dataset: str
    behavioural_spine: tuple[str, ...]
    transformation: str
    target_sourcetypes: tuple[str, ...]
    expected_recoverable_level: str
    injected_at: float
    anchor_entity: str = ""
    # How many real pivot hops `anchor_entity` sits from the technique's own
    # confirmed entity (`entities[0]`). 0 is a CONTROL, not a result: it
    # measures whether the anchor query finds its own entity, not whether an
    # investigation can reach anything (A4).
    planted_distance: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cousin_id": self.cousin_id,
            "parent_technique": self.parent_technique,
            "parent_dataset": self.parent_dataset,
            "behavioural_spine": list(self.behavioural_spine),
            "transformation": self.transformation,
            "target_sourcetypes": list(self.target_sourcetypes),
            "expected_recoverable_level": self.expected_recoverable_level,
            "injected_at": self.injected_at,
            "anchor_entity": self.anchor_entity,
            "planted_distance": self.planted_distance,
            "is_control": self.planted_distance == 0,
        }


class CousinOutsideCorpusRangeError(ValueError):
    """A cousin's `injected_at` falls outside the corpus's real time range.
    Raised instead of silently shipping a needle the haystack's own time
    bounds can never reach (I5) -- the T.3 configuration (2026 timestamps
    against a 2016-2019 corpus) is a permanent regression case for this."""


def validate_cousin_in_range(
    cousin: CousinSpec, *, corpus_earliest: float, corpus_latest: float
) -> None:
    if not (corpus_earliest <= cousin.injected_at <= corpus_latest):
        raise CousinOutsideCorpusRangeError(
            f"cousin_outside_corpus_range: {cousin.cousin_id} injected_at="
            f"{cousin.injected_at} is outside the corpus's real range "
            f"[{corpus_earliest}, {corpus_latest}]"
        )


# Transformations that make an injected chain a genuine COUSIN rather than a
# copy. RESCHEMA/REVOCABULARY are recoverable only at the behavioural level --
# which is the whole claim.
COUSIN_TRANSFORMATIONS: tuple[str, ...] = (
    "REVOCABULARY",  # same spine, different verbs in the same sourcetype
    "RESCHEMA",  # same spine, expressed in a DIFFERENT real sourcetype
    "REIDENTITY",  # same spine, principals never seen in the corpus
    "SCATTER",  # spine split across several sourcetypes/identities
    "REORDER_MINOR",  # benign steps interleaved into the spine
)


def plan_cousins(
    answer_key: list[AnswerKeyEntry],
    *,
    corpus_earliest: float,
    corpus_latest: float,
    transformations: tuple[str, ...] = COUSIN_TRANSFORMATIONS,
    corpus_sourcetypes: tuple[str, ...] = (),
    per_technique: int = 1,
) -> list[CousinSpec]:
    """Plan one cousin per (confirmed technique, transformation), placed
    INSIDE the corpus's own time range (I5).

    Deliberately derived FROM the answer key: a cousin is only meaningful as a
    variant of something we know is genuinely present. Inventing both the
    haystack and the needle -- what every prior run did -- makes recall a
    measurement of the generator.

    `corpus_earliest`/`corpus_latest` are required, not defaulted, because a
    cousin planned with no real range to sit inside of is exactly the T.3
    defect (cousins shipped at "now", ~8 years outside every BOTS index).
    Each cousin lands adjacent to its parent's own confirmed activity when
    `entry.confirmed_at` is known, otherwise spread deterministically across
    the corpus span -- either way inside `[corpus_earliest, corpus_latest]`.
    """
    if corpus_latest <= corpus_earliest:
        raise ValueError(
            f"corpus_latest ({corpus_latest}) must be after corpus_earliest ({corpus_earliest})"
        )
    span = corpus_latest - corpus_earliest
    specs: list[CousinSpec] = []
    for e_i, entry in enumerate(answer_key):
        # `entities_by_distance` carries real, live-discovered entities at
        # known pivot hops from the technique's own confirmed entity (A4).
        # 0 hops always falls back to `entities[0]` -- the pre-A4 behaviour,
        # kept as the CONTROL distance -- when no chain was discovered.
        distances = dict(entry.entities_by_distance)
        distances.setdefault(0, entry.entities[0] if entry.entities else "")
        distance_keys = sorted(k for k in distances if distances[k])
        if not distance_keys:
            distance_keys = [0]
            distances = {0: ""}
        for t_i, transformation in enumerate(transformations):
            for n in range(per_technique):
                # Cycle deterministically through every known distance so a
                # run plants cousins at 0/1/2/3 hops rather than only ever
                # at the parent's own entity -- I.6's shape, where every
                # cousin's `anchor_entity` equalled the anchor's entity and
                # `20/20` recovery measured planting position, not reach.
                slot_idx = t_i * per_technique + n
                planted_distance = distance_keys[slot_idx % len(distance_keys)]
                anchor_entity = distances[planted_distance]
                targets = entry.sourcetypes
                if transformation == "RESCHEMA" and corpus_sourcetypes:
                    # express it in a real sourcetype the parent did NOT use
                    alt = tuple(s for s in corpus_sourcetypes if s not in entry.sourcetypes)
                    targets = alt[:1] or entry.sourcetypes
                elif transformation == "SCATTER" and corpus_sourcetypes:
                    targets = tuple(corpus_sourcetypes[:3])

                if entry.confirmed_at is not None:
                    # Adjacent to the parent's own real activity, offset per
                    # (transformation, n) so cousins of the same parent don't
                    # collide, and clamped back inside the corpus's range.
                    offset = (t_i * per_technique + n + 1) * 300.0
                    injected_at = min(
                        max(entry.confirmed_at + offset, corpus_earliest), corpus_latest
                    )
                else:
                    # No known confirmation time: spread deterministically
                    # across the corpus span rather than collapsing onto one
                    # instant.
                    slot = (e_i * len(transformations) * per_technique) + (t_i * per_technique + n)
                    total_slots = len(answer_key) * len(transformations) * per_technique
                    fraction = (slot + 1) / (total_slots + 1) if total_slots else 0.5
                    injected_at = corpus_earliest + span * fraction

                specs.append(
                    CousinSpec(
                        # Qualified by dataset AND entry index (F.3,
                        # TASK_BULLY_FULL_ASSEMBLY_V1): the answer key scaled
                        # from 4 entries (one per technique) to dozens, where
                        # the SAME technique legitimately recurs across
                        # datasets and entries (T1190 in botsv1's Joomla
                        # exploit and botsv3's Struts2 exploit, for example).
                        # A cousin_id keyed on technique alone collided the
                        # moment two entries shared one, silently merging two
                        # cousins' `| delete` rollback tags into one.
                        cousin_id=(
                            f"cz-{entry.dataset}-{entry.technique}-{e_i:03d}-"
                            f"{transformation}-{t_i}{n}-d{planted_distance}"
                        ),
                        parent_technique=entry.technique,
                        parent_dataset=entry.dataset,
                        behavioural_spine=entry.behavioural_spine,
                        transformation=transformation,
                        target_sourcetypes=targets,
                        expected_recoverable_level=(
                            "L3_BEHAVIOR"
                            if transformation in ("REVOCABULARY", "RESCHEMA", "SCATTER")
                            else "L2_TOOL"
                        ),
                        injected_at=injected_at,
                        anchor_entity=anchor_entity,
                        planted_distance=planted_distance,
                    )
                )
    return specs


@dataclass(frozen=True)
class BedAcceptance:
    """The three numbers that make a run interpretable, kept apart on purpose."""

    floor_known_recall: float | None  # answer-key techniques recovered
    product_cousin_recall: float | None  # injected cousins recovered
    cost_background_fp_rate: float | None  # concerns on real benign traffic
    n_answer_key: int
    n_cousins_injected: int
    n_background_sampled: int
    verdict: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "floor_known_recall": self.floor_known_recall,
            "product_cousin_recall": self.product_cousin_recall,
            "cost_background_fp_rate": self.cost_background_fp_rate,
            "n_answer_key": self.n_answer_key,
            "n_cousins_injected": self.n_cousins_injected,
            "n_background_sampled": self.n_background_sampled,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }


def bed_acceptance(
    *,
    answer_key_hit: int,
    answer_key_total: int,
    cousin_hit: int,
    cousin_total: int,
    background_flagged: int,
    background_total: int,
    bed: BedReport,
    max_background_fp: float = 0.10,
) -> BedAcceptance:
    """Floor, product and cost as three separate numbers.

    Collapsing them is how a run reports success while finding nothing: a high
    combined 'recall' can be entirely floor (matching the answer key we were
    handed) with zero product (cousins). They are never averaged here.
    """
    floor = (answer_key_hit / answer_key_total) if answer_key_total else None
    product = (cousin_hit / cousin_total) if cousin_total else None
    cost = (background_flagged / background_total) if background_total else None

    reasons: list[str] = []
    verdict = "PASS"
    if not bed.is_haystack:
        verdict = "INVALID"
        reasons.extend(bed.reasons)
    if cousin_total == 0:
        verdict = "INVALID" if verdict != "INVALID" else verdict
        reasons.append("no_cousins_injected: the product claim is unmeasured")
    if product is not None and product == 0.0 and cousin_total:
        verdict = "FAIL" if verdict == "PASS" else verdict
        reasons.append("zero_cousin_recall: floor only, no product")
    if floor is not None and floor == 0.0 and answer_key_total:
        # T5, TASK_BULLY_REAL_TELEMETRY_V1: a system that cannot find a
        # single one of the corpus's own PUBLISHED known-bads has a broken
        # floor, and any product/cousin recall reported beside it is
        # unmeasurable noise -- C.6 came out FAIL only via the background FP
        # rate while floor_known_recall sat at 0.0 unexamined. FAIL, not
        # merely INVALID, so this holds even when the bed itself is fine.
        verdict = "FAIL" if verdict == "PASS" else verdict
        reasons.append(f"zero_floor_recall: 0/{answer_key_total}")
    if cost is not None and cost > max_background_fp:
        verdict = "FAIL" if verdict == "PASS" else verdict
        reasons.append(f"background_fp_rate_{cost:.3f}>{max_background_fp}")
    return BedAcceptance(
        floor_known_recall=floor,
        product_cousin_recall=product,
        cost_background_fp_rate=cost,
        n_answer_key=answer_key_total,
        n_cousins_injected=cousin_total,
        n_background_sampled=background_total,
        verdict=verdict,
        reasons=tuple(reasons),
    )


class RunOutputMissingBedAcceptanceError(ValueError):
    """A run published recovery figures (`reach_report`, cousin recovery,
    an inference report, ...) without publishing `bed_acceptance` alongside
    them (A5). Without it there is no way to tell whether the run stood on a
    haystack or a sample, so any recovery figure in the same document is
    INVALID -- refused outright rather than trusted at face value."""


def require_bed_acceptance(run_output: dict[str, Any]) -> None:
    """Every run doc that publishes recovery figures must publish
    `bed_acceptance` in the same document. Raises when it is missing or not
    a real acceptance verdict (`None`, or a dict lacking a `verdict`)."""
    acceptance = run_output.get("bed_acceptance")
    if not isinstance(acceptance, dict) or "verdict" not in acceptance:
        raise RunOutputMissingBedAcceptanceError(
            "run output is missing bed_acceptance -- a run publishing recovery "
            "figures without it is INVALID (A5, TASK_BULLY_ADAPTIVE_REACH_V1)"
        )


def stream_corpus(
    connector_factory: Callable[[str], Any],
    indexes: tuple[str, ...],
    *,
    batch_size: int = 10_000,
    max_records: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream every record across every index in batches.

    A corpus of millions cannot be read into memory, and a 2,000-row cap is
    what made the haystack invisible. Callers fit the baseline incrementally
    from this stream and score afterwards -- fit wide, score narrow.
    """
    emitted = 0
    for index in indexes:
        connector = connector_factory(index)
        offset = 0
        while True:
            if max_records is not None and emitted >= max_records:
                return
            take = batch_size
            if max_records is not None:
                take = min(take, max_records - emitted)
            rows = connector.fetch(offset=offset, limit=take)
            if not rows:
                break
            for row in rows:
                row["__index"] = index
                yield row
                emitted += 1
            offset += len(rows)
