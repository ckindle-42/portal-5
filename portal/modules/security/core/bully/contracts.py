"""bully.contracts -- versioned boundary DTOs + closed enums (P1.1).

Every command DTO carries `command_id, idempotency_key, expected_version,
actor, correlation_id` (FINAL_INTERFACES preamble). All DTOs here are
immutable (frozen dataclasses), JSON-serializable via `to_dict`, and
schema-versioned so a later field addition never silently reinterprets an
old persisted payload.

Pure module: no I/O, no imports from store/organ/network. Boundary rules
(MASTER SS3) forbid anything else from doing SQL or projection I/O; this
module only defines the shapes that cross those boundaries.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

# ── Closed enums (DATA_MODEL / INTERFACES) ──────────────────────────────────

RELATIONSHIPS: tuple[str, ...] = (
    "SAME",
    "SIMILAR",
    "NEW",
    "DIFFERENT",
    "ANOMALOUS_UNCLASSIFIED",
)

RESPONSES: tuple[str, ...] = (
    "COVERED",
    "NEAR_MISS",
    "MISSED",
    "INDETERMINATE",
)

DRIFT_CLASSES: tuple[str, ...] = (
    "TELEMETRY_DEGRADATION",
    "ENVIRONMENT_CHANGE",
    "ATTACKER_EVOLUTION",
    "DETECTION_DEGRADATION",
    "UNCLASSIFIED",
)

TRUST_TIERS: tuple[str, ...] = (
    "VALIDATED",
    "OPERATOR_CONFIRMED",
    "SUSPECT",
    "IMPORTED_UNVERIFIED",
    "SUPERSEDED",
)

HUNT_STAGES: tuple[str, ...] = (
    "DRAFT",
    "AUTHORIZED",
    "RECALL_READY",
    "TARGETED",
    "MUTATION_READY",
    "EXECUTING",
    "ANALYZING",
    "PROMOTING",
    "COMPOUNDING",
    "CLOSED",
    "BLOCKED",
    "CANCELLED",
    "FAILED",
)

# Legal forward transitions only (I-3); no backward transition, ever, except
# into the three terminal-adjacent recovery stages from any non-terminal stage.
_TERMINAL_ADJACENT: frozenset[str] = frozenset({"BLOCKED", "CANCELLED", "FAILED"})
_HUNT_STAGE_ORDER: dict[str, int] = {
    name: i
    for i, name in enumerate(
        (
            "DRAFT",
            "AUTHORIZED",
            "RECALL_READY",
            "TARGETED",
            "MUTATION_READY",
            "EXECUTING",
            "ANALYZING",
            "PROMOTING",
            "COMPOUNDING",
            "CLOSED",
        )
    )
}


def is_legal_hunt_transition(current: str, target: str) -> bool:
    """Stage machine legality check (I-3 / C1 "rejects illegal transitions").

    Forward-only through the main sequence, or into a terminal-adjacent
    recovery stage (BLOCKED/CANCELLED/FAILED) from any non-terminal stage.
    Never legal to move backward in the main sequence, and never legal to
    leave CLOSED/CANCELLED/FAILED (true terminal states).
    """
    if current not in HUNT_STAGES or target not in HUNT_STAGES:
        raise ValueError(f"unknown hunt stage: {current!r} -> {target!r}")
    if current in ("CLOSED", "CANCELLED", "FAILED"):
        return False
    if target in _TERMINAL_ADJACENT:
        return current != "CLOSED"
    if current == "BLOCKED":
        # BLOCKED resumes back into the stage it was blocked from is handled
        # by the orchestrator re-driving from last committed event, not by a
        # generic transition here; BLOCKED -> main sequence is not a bare
        # forward step, so contracts.py only allows BLOCKED -> CANCELLED/FAILED.
        return False
    return _HUNT_STAGE_ORDER.get(target, -1) > _HUNT_STAGE_ORDER.get(current, -1)


DECISION_EVENT_KINDS: tuple[str, ...] = (
    "target_select",
    "grade",
    "gate",
    "council_block",
    "objection",
    "waiver",
    "promote",
    "kill",
    "plateau",
    "roster",
    "playbook",
    "train",
    "config",
    "recall",
    "impact",
)

OUTBOX_STATUSES: tuple[str, ...] = ("pending", "leased", "completed", "dead_letter")
OUTBOX_OPERATIONS: tuple[str, ...] = ("upsert", "tombstone")


# ── DTO base ─────────────────────────────────────────────────────────────────


def new_id(prefix: str) -> str:
    """Time-derived id: `<prefix>-<ISO>-<hash8>` (DATA_MODEL SS4.1)."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{prefix}-{ts}-{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class CommandEnvelope:
    """Fields every command DTO carries (FINAL_INTERFACES preamble)."""

    command_id: str
    idempotency_key: str
    expected_version: int | None
    actor: str
    correlation_id: str

    @classmethod
    def new(
        cls,
        *,
        actor: str,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        expected_version: int | None = None,
    ) -> CommandEnvelope:
        return cls(
            command_id=new_id("cmd"),
            idempotency_key=idempotency_key or new_id("idem"),
            expected_version=expected_version,
            actor=actor,
            correlation_id=correlation_id or new_id("corr"),
        )


class _DTOMixin:
    """Shared (de)serialization for frozen dataclasses defined below."""

    schema_version: ClassVar[int] = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)  # type: ignore[call-overload]
        d["_schema_version"] = self.schema_version
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        payload = {k: v for k, v in data.items() if k != "_schema_version"}
        return cls(**payload)

    @classmethod
    def from_json(cls, text: str) -> Any:
        return cls.from_dict(json.loads(text))


# ── DecisionEvent (SS1.9) ────────────────────────────────────────────────────


@dataclass(frozen=True)
class DecisionEvent(_DTOMixin):
    """Append-only, hash-chained provenance record (DATA_MODEL SS1.9)."""

    event_id: str
    hunt_id: str | None
    iteration_id: str | None
    actor: str
    kind: str
    subject_id: str
    rationale: str
    data: dict[str, Any] = field(default_factory=dict)
    prev_event_hash: str | None = None
    chain_hash: str | None = None
    occurred_at: float = field(default_factory=time.time)
    recorded_at: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in DECISION_EVENT_KINDS:
            raise ValueError(f"unknown decision-event kind: {self.kind!r}")
        if not self.rationale:
            raise ValueError("DecisionEvent.rationale is mandatory")


# ── RecallReceipt / DecisionImpact (I-4, SS1.11) ─────────────────────────────


@dataclass(frozen=True)
class RecallReceipt(_DTOMixin):
    """Mandatory pre-hunt recall proof (I-4). Persisted even when empty/degraded."""

    recall_id: str
    hunt_id: str
    query: str
    filters: dict[str, Any]
    source_health: dict[str, Any]
    projection_version: str
    embedding_version: str
    reranker_version: str | None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    exclusions: list[dict[str, Any]] = field(default_factory=list)
    selected_context: list[dict[str, Any]] = field(default_factory=list)
    token_budget: int | None = None
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class DecisionImpact(_DTOMixin):
    """Auditable compounding-chain link: what a recall changed (SS1.11)."""

    impact_id: str
    recall_id: str
    consuming_decision_ref: str
    before: dict[str, Any]
    after: dict[str, Any]
    cited_record_ids: list[str]
    change_kind: str  # SELECTED|DEPRIORITIZED|AVOIDED|CONTROL_ADDED|NO_EFFECT
    explanation: str
    created_at: float = field(default_factory=time.time)

    _CHANGE_KINDS: ClassVar[tuple[str, ...]] = (
        "SELECTED",
        "DEPRIORITIZED",
        "AVOIDED",
        "CONTROL_ADDED",
        "NO_EFFECT",
    )

    def __post_init__(self) -> None:
        if self.change_kind not in self._CHANGE_KINDS:
            raise ValueError(f"unknown DecisionImpact.change_kind: {self.change_kind!r}")


# ── CousinAssessment (I-6, SS1.4) ────────────────────────────────────────────


@dataclass(frozen=True)
class Decomposition(_DTOMixin):
    behavior: float | None
    telemetry: float | None
    semantic: float | None
    attack: float | None
    context: float | None


@dataclass(frozen=True)
class CousinAssessment(_DTOMixin):
    """Two-axis grading result (I-6). Immutable; a re-grade supersedes."""

    assessment_id: str
    subject_signature_id: str
    reference_signature_id: str | None
    candidate_set_id: str
    decomposition: Decomposition
    composite: float
    relationship: str
    nonsemantic_channels: int
    vetoes: list[dict[str, Any]]
    defense_response: str
    nearest_knowns: list[tuple[str, float]]
    confidence: float
    completeness: float
    algorithm_version: str
    thresholds_version: str
    explanation: dict[str, Any] = field(default_factory=dict)
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if self.relationship not in RELATIONSHIPS:
            raise ValueError(f"unknown relationship: {self.relationship!r}")
        if self.defense_response not in RESPONSES:
            raise ValueError(f"unknown defense_response: {self.defense_response!r}")
        if self.relationship in ("SIMILAR", "NEW") and self.nonsemantic_channels < 2:
            raise ValueError(
                f"{self.relationship} requires >=2 non-semantic channels "
                f"(got {self.nonsemantic_channels}) -- C5 CLAIM 4"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CousinAssessment:
        payload = dict(data)
        payload.pop("_schema_version", None)
        decomp = payload.get("decomposition")
        if isinstance(decomp, dict):
            payload["decomposition"] = Decomposition.from_dict(decomp)
        nk = payload.get("nearest_knowns")
        if nk is not None:
            payload["nearest_knowns"] = [tuple(x) for x in nk]
        return cls(**payload)


# ── HuntContext (transient, SS3) ─────────────────────────────────────────────


@dataclass(frozen=True)
class HuntContext(_DTOMixin):
    """SUB snapshot handed to LOOP at hunt start (DATA_MODEL SS3)."""

    hunt_id: str
    neighborhood_scope: str
    config_version: str
    open_cells: list[dict[str, Any]] = field(default_factory=list)
    known_state_view: list[dict[str, Any]] = field(default_factory=list)
    plateau_view: dict[str, Any] | None = None
    cost_view: dict[str, Any] | None = None


def round_trip(dto: _DTOMixin) -> Any:
    """Serialize then deserialize -- used by the P1.1 round-trip tests."""
    return type(dto).from_json(dto.to_json())
