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

DRIFT_FLAG_STATUSES: tuple[str, ...] = ("FLAGGED", "INSUFFICIENT_BASELINE")

BASELINE_STATUSES: tuple[str, ...] = ("warmup", "active", "superseded")

# ── Mutation director (MUT, I-1/I-20, P3.1) ─────────────────────────────────

# The typed-operator catalog itself (code-level, closed). hunt.yaml's
# `mutation.allowed_classes` is a *separate*, narrower, operator-confirmed
# subset of this catalog per hunt (the `[GATE]` in I-1: "new/widened
# mutation classes require explicit operator confirmation") -- this tuple is
# what a class name must belong to before that per-hunt approval check even
# applies.
MUTATION_OPERATORS: tuple[str, ...] = (
    "REORDER_STEPS",
    "SUBSTITUTE_TECHNIQUE",
    "VARY_PARAMETER",
    "INJECT_EVASION_DIRECTIVE",
    "OFF_SCRIPT_SUPPLY",
    "REVERSE_GEN_SEED",
)

MUTATION_BUDGET_CLASSES: tuple[str, ...] = ("minimal", "standard", "extended")

# Named invariants a plan may declare (checked for conflict against its own
# operator set at validation time -- P3.1 "invariant conflict").
MUTATION_INVARIANTS: tuple[str, ...] = (
    "preserve_mission_objective",
    "preserve_final_step",
    "single_technique_only",
    "no_new_techniques",
)

# ── Cost metering (COST, I-13, P4.1) ────────────────────────────────────────

COST_METERS: tuple[str, ...] = (
    "lab_minutes",
    "inference_calls",
    "inference_tokens",
    "inference_latency_ms",
    "analyst_minutes",
    "replay_work",
    "storage_bytes",
    "training_allocation",
)

MEASUREMENT_QUALITIES: tuple[str, ...] = ("measured", "estimated", "missing")

# ── Targeting (TGT, I-11, P4.3) ──────────────────────────────────────────────

TARGET_DECLINE_REASONS: tuple[str, ...] = (
    "KNOWN_BENIGN",
    "UNAUTHORIZED",
    "NOT_READY",
    "UNHEALTHY",
    "LOCKED",
    "MISSING_COST",
)

TARGET_DECISION_STATUSES: tuple[str, ...] = (
    "selected",
    "no_eligible_target",
    "unrankable",
)

# ── Plateau (PLT, I-12, P4.4) ────────────────────────────────────────────────

PLATEAU_DECISIONS: tuple[str, ...] = ("CONTINUE", "PLATEAU", "INSUFFICIENT")
PLATEAU_ACTIONS: tuple[str, ...] = ("continue", "rotate", "stop")

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


# ── BIN state machine (I-7, P2.1) ───────────────────────────────────────────

CANDIDATE_STATES: tuple[str, ...] = (
    "CREATED",
    "G_MINUS_1_PASS",
    "G0_PASS",
    "G1A_PASS",
    "G1B_PASS",
    "G2_PASS",
    "COUNCIL_PASS",
    "G3_PASS",
    "AWAITING_OPERATOR",
    "PROMOTED",
    "DISPROVED",
    "BLOCKED",
    "KILLED",
    "OPERATOR_ESCALATED",
)

GATE_IDS: tuple[str, ...] = ("G-1", "G0", "G1a", "G1b", "G2", "G4", "G3", "G5")
GATE_OUTCOMES: tuple[str, ...] = ("pass", "fail", "blocked")

# The candidates.current_state main sequence, in strict forward order. A
# candidate advances one hop at a time through this sequence (no
# skip-a-gate); HEART's clearance is persisted as a gate_results row with
# gate_id='G5' between G2 and G3 (SS4.8's "gates + a G5 record").
_BIN_TERMINAL_ADJACENT: frozenset[str] = frozenset(
    {"BLOCKED", "KILLED", "DISPROVED", "OPERATOR_ESCALATED"}
)
_BIN_MAIN_ORDER: dict[str, int] = {
    name: i
    for i, name in enumerate(
        (
            "CREATED",
            "G_MINUS_1_PASS",
            "G0_PASS",
            "G1A_PASS",
            "G1B_PASS",
            "G2_PASS",
            "COUNCIL_PASS",
            "G3_PASS",
            "AWAITING_OPERATOR",
            "PROMOTED",
        )
    )
}


def is_legal_bin_transition(current: str, target: str) -> bool:
    """BIN state-machine legality (I-7 / C7 "illegal skip-a-gate transition
    rejected"). Forward-only, one hop at a time through the gate sequence,
    or into a terminal-adjacent recovery state (BLOCKED/KILLED/DISPROVED/
    OPERATOR_ESCALATED) from any non-terminal state. Only AWAITING_OPERATOR
    may advance to PROMOTED (operator-only, enforced by the caller checking
    `actor`, not by this pure function). BLOCKED/OPERATOR_ESCALATED never
    bare-transition onward -- resumption re-drives the specific gate that
    was blocked/escalated via `promotion.process`, not a generic hop here.
    """
    if current not in CANDIDATE_STATES or target not in CANDIDATE_STATES:
        raise ValueError(f"unknown candidate state: {current!r} -> {target!r}")
    if current in ("PROMOTED", "DISPROVED", "KILLED"):
        return False
    if target in _BIN_TERMINAL_ADJACENT:
        return True
    if target == "PROMOTED":
        return current == "AWAITING_OPERATOR"
    if current in ("BLOCKED", "OPERATOR_ESCALATED"):
        return False
    cur_i = _BIN_MAIN_ORDER.get(current, -1)
    tgt_i = _BIN_MAIN_ORDER.get(target, -1)
    return tgt_i == cur_i + 1


# ── Council / objection gate (I-8, P2.1) ────────────────────────────────────

OBJECTION_CATEGORIES: tuple[str, ...] = (
    "evidence_contradiction",
    "covering_detection_id",
    "benign_counter_evidence",
    "scope_safety",
    "reproducibility",
    "telemetry_health",
    "relationship_classification",
    "defense_response",
    "analyst_visibility",
    "regression_risk",
)

OBJECTION_STATUSES: tuple[str, ...] = (
    "open",
    "rebutted",
    "re_review",
    "withdrawn",
    "sustained",
    "waived",
    "superseded",
)

# ── Promotion queue (I-3/I-7, SS4.8) ────────────────────────────────────────

QUEUE_ITEM_KINDS: tuple[str, ...] = (
    "cousin_detection",
    "model",
    "playbook",
    "roster",
    "waiver",
    "policy",
    "review_escalation",
)
QUEUE_STATES: tuple[str, ...] = ("pending", "confirmed", "rejected")


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
    "handoff",
    "deploy",
)

# ── Detection proposals (HND, P5.1, DATA_MODEL SS1.20) ──────────────────────

PROPOSAL_STATES: tuple[str, ...] = (
    "draft",
    "submitted",
    "accepted",
    "revise",
    "rejected",
    "expired",
    "deployed",
    "replay-validated",
    "replay-failed",
    "retired",
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


# ── Candidate / GateResult / BinOutcome (I-7, SS1.5) ────────────────────────


@dataclass(frozen=True)
class Candidate(_DTOMixin):
    """Suspect-until-proven promotion-pipeline row (I-7, SS1.5)."""

    candidate_id: str
    hunt_id: str
    assessment_id: str
    evidence_manifest_id: str | None
    alert_version: int
    current_state: str
    gate_policy_version: str
    terminal_reason: str | None = None
    queue_state: str | None = None
    decided_by: str | None = None
    decided_at: float | None = None
    rationale: str | None = None
    version: int = 0
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.current_state not in CANDIDATE_STATES:
            raise ValueError(f"unknown candidate state: {self.current_state!r}")


@dataclass(frozen=True)
class GateResult(_DTOMixin):
    """One gate attempt (I-7 "Gate internals"). Re-runnable; attempts are
    separately numbered; UNIQUE(candidate_id, alert_version, gate_id, attempt)."""

    result_id: str
    candidate_id: str
    alert_version: int
    gate_id: str
    attempt: int
    outcome: str
    validator_version: str
    inputs: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.gate_id not in GATE_IDS:
            raise ValueError(f"unknown gate_id: {self.gate_id!r}")
        if self.outcome not in GATE_OUTCOMES:
            raise ValueError(f"unknown gate outcome: {self.outcome!r}")


@dataclass(frozen=True)
class BinOutcome(_DTOMixin):
    """`promotion.process` return value (I-7)."""

    candidate_id: str
    state: str
    gate_results: dict[str, str] = field(default_factory=dict)  # gate_id -> outcome
    council_record_ref: str | None = None
    queue_id: str | None = None
    rationale: str = ""


# ── Council (HEART, I-8, SS1.6) ──────────────────────────────────────────────


@dataclass(frozen=True)
class CouncilOpinionRecord(_DTOMixin):
    """One seat's persisted opinion (SS1.6 `council_opinions`). Distinct from
    (but built from) `portal.platform.inference.router.council.CouncilOpinion`
    -- this is the bully-persisted shape, one row per (packet, seat, attempt)."""

    opinion_id: str
    packet_id: str
    seat_id: str
    attempt: int
    member_id: str
    model: str
    family: str
    valid: bool
    recommendation: str = ""
    confidence: float = 0.0
    error: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    strongest_objection: str = ""
    missing_evidence: list[str] = field(default_factory=list)
    conditions_to_change: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Objection(_DTOMixin):
    objection_id: str
    packet_id: str
    seat_id: str
    category: str
    material: bool
    claim: str
    evidence_citations: list[str] = field(default_factory=list)
    missing_proof_citations: list[str] = field(default_factory=list)
    status: str = "open"
    age_seconds: float | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.category not in OBJECTION_CATEGORIES:
            raise ValueError(f"unknown objection category: {self.category!r}")
        if self.status not in OBJECTION_STATUSES:
            raise ValueError(f"unknown objection status: {self.status!r}")


@dataclass(frozen=True)
class Rebuttal(_DTOMixin):
    rebuttal_id: str
    objection_id: str
    author: str
    claim: str
    evidence_citations: list[str] = field(default_factory=list)
    requested_review: str | None = None
    re_review_result: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class CouncilRecord(_DTOMixin):
    """`adversary.review` return value (I-8)."""

    packet_id: str
    candidate_id: str
    evidence_manifest_hash: str
    materiality_version: str
    roster_snapshot: dict[str, Any]
    opinions: list[CouncilOpinionRecord]
    objections: list[Objection]
    rebuttals: list[Rebuttal]
    unresolved: bool
    review_valid: bool
    participation: float
    created_at: float = field(default_factory=time.time)


# ── SOC visibility (G3, I-7a) ────────────────────────────────────────────────


@dataclass(frozen=True)
class SOCDeliveryReceipt(_DTOMixin):
    delivery_id: str
    candidate_id: str
    correlation_key: str
    producer_ack: bool
    consumer_query_ran: bool
    consumer_triage_report: dict[str, Any] | None
    priority: str
    latency_s: float | None
    content_hash_match: bool
    load_profile: str
    created_at: float = field(default_factory=time.time)

    @property
    def sufficient(self) -> bool:
        """I-7a: "producer ack without a consumer query is insufficient."""
        return bool(self.producer_ack and self.consumer_query_ran and self.content_hash_match)


# ── MutationPlan / ScenarioOverlay (I-1/I-20, P3.1) ─────────────────────────


@dataclass(frozen=True)
class MutationOperatorSpec(_DTOMixin):
    """One typed operator instance within a MutationPlan."""

    operator: str
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.operator not in MUTATION_OPERATORS:
            raise ValueError(f"unknown mutation operator: {self.operator!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MutationOperatorSpec:
        payload = {k: v for k, v in data.items() if k != "_schema_version"}
        return cls(**payload)


@dataclass(frozen=True)
class MutationPlan(_DTOMixin):
    """Typed mutation plan (I-1). Data only -- never code changes to Red.

    Compiled by `bully/mutation.py::validate_and_compile` into a
    `ScenarioOverlay` handed to the unchanged `exec_chain._prepare_scenario`/
    `BenchConfig.set_scenario`.
    """

    plan_id: str
    plan_version: int
    reference_scenario: str
    operators: tuple[MutationOperatorSpec, ...]
    invariants: tuple[str, ...]
    expected_observables: dict[str, Any]
    controls: tuple[str, ...]
    replay_policy: str
    allowed_targets: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    cleanup: tuple[str, ...]
    approval_ref: str | None
    budget_class: str
    idempotency_key: str
    proposer: str
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.budget_class not in MUTATION_BUDGET_CLASSES:
            raise ValueError(f"unknown mutation budget_class: {self.budget_class!r}")
        for inv in self.invariants:
            if inv not in MUTATION_INVARIANTS:
                raise ValueError(f"unknown mutation invariant: {inv!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MutationPlan:
        payload = {k: v for k, v in data.items() if k != "_schema_version"}
        ops = payload.get("operators") or ()
        payload["operators"] = tuple(
            op if isinstance(op, MutationOperatorSpec) else MutationOperatorSpec.from_dict(op)
            for op in ops
        )
        for tuple_field in (
            "invariants",
            "controls",
            "allowed_targets",
            "allowed_tools",
            "cleanup",
        ):
            if tuple_field in payload and payload[tuple_field] is not None:
                payload[tuple_field] = tuple(payload[tuple_field])
        return cls(**payload)


@dataclass(frozen=True)
class ScenarioOverlay(_DTOMixin):
    """Rendered scenario overlay (I-1 OUTPUT): `red_prompt`, `red_order`,
    expectation metadata -- handed unchanged to `exec_chain._prepare_scenario`
    / `BenchConfig.set_scenario`. Compilation is a pure function of
    `(plan, reference_scenario, hunt_config)`: the same plan version yields a
    byte-identical `red_order`/`red_prompt`/`expectation` (`overlay_id` is
    deterministic in the plan; `created_at` is audit metadata only and is
    NOT part of the byte-identical guarantee -- MASTER SS0 anchor note)."""

    overlay_id: str
    plan_id: str
    plan_version: int
    reference_scenario: str
    red_order: tuple[str, ...]
    red_prompt: str
    mission_objective: str | None
    target_host: str | None
    expectation: dict[str, Any]
    applied_operators: tuple[str, ...]
    truncated: bool
    truncation_rationale: str | None
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScenarioOverlay:
        payload = {k: v for k, v in data.items() if k != "_schema_version"}
        for tuple_field in ("red_order", "applied_operators"):
            if tuple_field in payload and payload[tuple_field] is not None:
                payload[tuple_field] = tuple(payload[tuple_field])
        return cls(**payload)


# ── DriftFlag / DetectionBaseline (I-9, P3.2) ───────────────────────────────


@dataclass(frozen=True)
class DriftFlag(_DTOMixin):
    """Temporal-cousin drift flag (I-9 OUTPUT). `drift_class` is always one
    of `DRIFT_CLASSES`; `status` disambiguates a confident classification
    (`FLAGGED`) from an honest non-answer (`INSUFFICIENT_BASELINE`, paired
    with `drift_class="UNCLASSIFIED"`)."""

    flag_id: str
    detection_id: str
    episode_id: str
    drift_class: str
    status: str
    score: float
    signals: dict[str, Any] = field(default_factory=dict)
    bands: dict[str, Any] = field(default_factory=dict)
    breaches: dict[str, Any] = field(default_factory=dict)
    consecutive_count: int = 0
    routed: bool = False
    detail: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.drift_class not in DRIFT_CLASSES:
            raise ValueError(f"unknown drift class: {self.drift_class!r}")
        if self.status not in DRIFT_FLAG_STATUSES:
            raise ValueError(f"unknown drift flag status: {self.status!r}")


# ── Cost metering (I-13, P4.1) ───────────────────────────────────────────────


@dataclass(frozen=True)
class CostComponent(_DTOMixin):
    """One typed resource observation, keyed by `source_key` (idempotency
    unit: I-13 "one cost component per source key"). `value` is `None` iff
    `quality == "missing"` -- a missing material measurement is never
    zero-filled."""

    meter: str
    source_key: str
    value: float | None
    quality: str

    def __post_init__(self) -> None:
        if self.meter not in COST_METERS:
            raise ValueError(f"unknown cost meter: {self.meter!r}")
        if self.quality not in MEASUREMENT_QUALITIES:
            raise ValueError(f"unknown measurement quality: {self.quality!r}")
        if self.quality == "missing" and self.value is not None:
            raise ValueError("a 'missing' component must carry value=None -- never zero-filled")
        if self.quality != "missing" and self.value is None:
            raise ValueError(
                f"component {self.source_key!r} quality={self.quality!r} needs a value"
            )


@dataclass(frozen=True)
class CostRecord(_DTOMixin):
    """Per-hunt/iteration cost ledger row (I-13 OUTPUT, DATA_MODEL SS1.12).
    `computed_units` is `None` whenever any component is `quality="missing"`
    -- material missing measurement blocks ROI claims, it never zero-fills."""

    record_id: str
    hunt_id: str
    iteration_id: str | None
    components: tuple[CostComponent, ...]
    pricing_profile_version: str
    computed_units: float | None
    quality_flag: bool
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostRecord:
        payload = {k: v for k, v in data.items() if k != "_schema_version"}
        comps = payload.get("components") or ()
        payload["components"] = tuple(
            c if isinstance(c, CostComponent) else CostComponent.from_dict(c) for c in comps
        )
        return cls(**payload)


# ── Targeting (I-11, P4.3) ───────────────────────────────────────────────────


@dataclass(frozen=True)
class DeclinedCell(_DTOMixin):
    """One hard-ineligible cell + why (I-11 OUTPUT "declined cells with
    reasons")."""

    cell_id: str
    reason: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.reason not in TARGET_DECLINE_REASONS:
            raise ValueError(f"unknown decline reason: {self.reason!r}")


@dataclass(frozen=True)
class TargetDecision(_DTOMixin):
    """TGT's output (I-11): ordered targets + full factor breakdown, declined
    cells with reasons, recall influence, tie-break, and an honest terminal
    status when nothing is selectable."""

    decision_id: str
    hunt_id: str
    algorithm_version: str
    config_version: str
    status: str
    selected_cell_id: str | None
    ordered_targets: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    declined: tuple[DeclinedCell, ...] = field(default_factory=tuple)
    recall_influence: dict[str, Any] = field(default_factory=dict)
    tie_break: str | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.status not in TARGET_DECISION_STATUSES:
            raise ValueError(f"unknown target decision status: {self.status!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TargetDecision:
        payload = {k: v for k, v in data.items() if k != "_schema_version"}
        payload["ordered_targets"] = tuple(payload.get("ordered_targets") or ())
        declined = payload.get("declined") or ()
        payload["declined"] = tuple(
            d if isinstance(d, DeclinedCell) else DeclinedCell.from_dict(d) for d in declined
        )
        return cls(**payload)


# ── Plateau (I-12, P4.4) ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlateauDecision(_DTOMixin):
    """PLT's output (I-12, DATA_MODEL SS1.13): the classification
    (`decision`) plus the operator-facing action (`action`,
    continue|rotate|stop -- I-12's literal return-type comment); plateau is
    always neighborhood-local."""

    plateau_id: str
    hunt_id: str
    neighborhood: str
    qualifying_trial_ids: tuple[str, ...]
    promotions: int
    unique_response_gain: float
    posterior_upper_bound: float
    saturation: float
    policy_version: str
    decision: str
    action: str
    note: str = ""
    reset_trigger: str | None = None
    reset_version: str | None = None
    override: dict[str, Any] | None = None
    expiry: float | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.decision not in PLATEAU_DECISIONS:
            raise ValueError(f"unknown plateau decision: {self.decision!r}")
        if self.action not in PLATEAU_ACTIONS:
            raise ValueError(f"unknown plateau action: {self.action!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlateauDecision:
        payload = {k: v for k, v in data.items() if k != "_schema_version"}
        payload["qualifying_trial_ids"] = tuple(payload.get("qualifying_trial_ids") or ())
        return cls(**payload)


# ── HandoffPackage (HND, I-14, DESIGN SS23) ──────────────────────────────────


@dataclass(frozen=True)
class HandoffPackage(_DTOMixin):
    """The 11-part family-generalizing detection-engineering exit (DESIGN
    SS23). Built by `bully/handoff.py::build_package`; persisted as
    `detection_proposals.package_json` plus rendered files under
    `PORTAL5_HUNT_DIR/artifacts/` (I-14 STATE EFFECT)."""

    proposal_id: str
    candidate_id: str
    family: str
    # 1. generalized SPL + per-sourcetype variants (spl_variants shape)
    spl: str
    spl_variants: list[dict[str, Any]]
    # 2. Sigma rule (YAML text)
    sigma_rule: str
    # 3. required-telemetry statement
    required_telemetry: list[str]
    # 4. ATT&CK mapping delta
    attack_mapping_delta: dict[str, Any]
    # 5. evidence package (episode refs, gate history, council record)
    evidence_package: dict[str, Any]
    # 6. reproduction instructions = a new capture recipe (regression test)
    regression_recipe_name: str
    regression_recipe: dict[str, Any]
    # 7. FP analysis (G2 benign-corpus results)
    fp_analysis: dict[str, Any]
    # 8. known limitations
    known_limitations: list[str]
    # 9. IR implications (seeded from response_loop's RESPONSE_PRIMITIVES)
    ir_implications: list[dict[str, Any]]
    # 10. coverage-impact preview (SUB delta)
    coverage_impact_preview: dict[str, Any]
    # 11. rollout/rollback plan, owner, expiry
    rollout_plan: str
    rollback_plan: str
    owner: str
    expiry: float | None
    # proof-leg results (fires-on-attack / quiet-on-benign / no-regression)
    proof_legs: dict[str, Any]
    content_hash: str = ""
    created_at: float = field(default_factory=time.time)


def round_trip(dto: _DTOMixin) -> Any:
    """Serialize then deserialize -- used by the P1.1 round-trip tests."""
    return type(dto).from_json(dto.to_json())
