"""review.contracts -- the reviewer's data contracts and controlled vocabularies.

Truth classes (the compliance core's rule, applied here): every persisted statement is a
*source fact* (read from a data source), a *machine-derived* assertion (computed or inferred
by this system) or an *operator decision* (an analyst said so). A derived claim may never
masquerade as a source fact, and an analyst's verdict is never overwritten by the machine.

Examined and resolved are reported as separate counts everywhere (``StageReceipt``):
the reviewer reports comprehension, not exposure.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from typing import Any

from . import CONTRACT_VERSION

__all__ = [
    "CONCERN_OUTCOMES",
    "CONTRACT_VERSION",
    "AbsenceReceipt",
    "Channel",
    "Claim",
    "DefenseResponse",
    "EvidenceRef",
    "JudgeRecord",
    "Outcome",
    "Resemblance",
    "ReviewConcern",
    "ReviewResult",
    "StageReceipt",
    "TruthClass",
    "Verdict",
    "to_plain",
]


class TruthClass(StrEnum):
    SOURCE_FACT = "source_fact"
    MACHINE_DERIVED = "machine_derived"
    OPERATOR_DECISION = "operator_decision"


class Outcome(StrEnum):
    """Mirrors ``bully.unit_outcome.OUTCOMES`` so the engine and the product speak one language."""

    UNKNOWN_SAME = "UNKNOWN_SAME"
    COUSIN = "COUSIN"
    NOVEL = "NOVEL"
    KNOWN_INSTANCE = "KNOWN_INSTANCE"
    RECOGNIZED_NORMAL = "RECOGNIZED_NORMAL"
    NORMAL = "NORMAL"
    INSUFFICIENT_VIEW = "INSUFFICIENT_VIEW"


CONCERN_OUTCOMES: frozenset[Outcome] = frozenset(
    {Outcome.UNKNOWN_SAME, Outcome.COUSIN, Outcome.NOVEL}
)


class Verdict(StrEnum):
    """The analyst's (or judge's) call. ``UNSURE`` is a first-class answer, never an error."""

    SOMETHING = "something"
    NOTHING = "nothing"
    UNSURE = "unsure"


class Channel(StrEnum):
    UNUSUAL = "unusual"
    KNOWN_SIMILAR = "known_similar"


class DefenseResponse(StrEnum):
    """Would existing detection content have fired on this unit's events?

    ``INDETERMINATE`` is the default and the only honest value until a detection has actually
    been evaluated against the unit; nothing in this package defaults to ``COVERED``.
    """

    COVERED = "COVERED"
    NEAR_MISS = "NEAR_MISS"
    MISSED = "MISSED"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class EvidenceRef:
    event_id: str
    source_id: str
    time: float | None = None
    truth_class: TruthClass = TruthClass.SOURCE_FACT


@dataclass(frozen=True)
class Claim:
    """One assertion. It must cite at least one evidence id; ``quote`` (optional) must appear
    verbatim in a cited event -- both are checked deterministically (``grounding``)."""

    text: str
    evidence_ids: tuple[str, ...]
    quote: str | None = None
    truth_class: TruthClass = TruthClass.MACHINE_DERIVED


@dataclass(frozen=True)
class Resemblance:
    """What a unit resembles. ``anchor_label`` is knowledge about the KNOWN thing."""

    anchor_id: str
    anchor_kind: str
    anchor_label: str
    similarity: float
    empirical_p: float
    malice: str = "unknown"
    shares: tuple[str, ...] = ()
    diverges: tuple[str, ...] = ()


@dataclass(frozen=True)
class AbsenceReceipt:
    """Absence is recorded, never inferred: what was searched, under which embedder, against
    which calibrated threshold. 'Nothing known resembles this' is only claimable with this."""

    population: int
    kinds: tuple[str, ...]
    embedder_id: str
    closest_similarity: float | None
    threshold: float | None
    calibration_id: str
    statement: str


@dataclass
class JudgeRecord:
    model: str
    verdict: Verdict
    confidence: float = 0.0
    claims: tuple[Claim, ...] = ()
    dropped_claims: int = 0
    challenger_verdict: str = ""
    panel: dict[str, Any] = field(default_factory=dict)
    rounds: int = 0
    degraded: str = ""
    note: str = ""
    evidence_shown: int = 0
    evidence_total: int = 0


@dataclass
class ReviewConcern:
    concern_id: str
    unit_id: str
    level: str
    outcome: Outcome
    channels: tuple[Channel, ...]
    priority_p: float
    unusual_p: float | None = None
    similar_p: float | None = None
    entities: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    span_seconds: float | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    resembles: tuple[Resemblance, ...] = ()
    absence: AbsenceReceipt | None = None
    brief: str = ""
    judge: JudgeRecord | None = None
    defense_response: DefenseResponse = DefenseResponse.INDETERMINATE
    truth_class: TruthClass = TruthClass.MACHINE_DERIVED


@dataclass(frozen=True)
class StageReceipt:
    name: str
    examined: int
    resolved: int
    note: str = ""


@dataclass
class ReviewResult:
    run_id: str
    fingerprint: dict[str, str]
    concerns: list[ReviewConcern] = field(default_factory=list)
    suppressed: list[ReviewConcern] = field(default_factory=list)
    receipts: list[StageReceipt] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0


def to_plain(obj: Any) -> Any:
    """JSON-safe projection of contract objects (enums to values, dataclasses to dicts)."""
    if isinstance(obj, StrEnum):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_plain(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        return sorted((to_plain(v) for v in obj), key=str)
    if isinstance(obj, (list, tuple)):
        return [to_plain(v) for v in obj]
    return obj
