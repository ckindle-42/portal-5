"""Typed row schemas for the canonical compliance store (P2).

These dataclasses mirror the tables in ``core/migrations``. Only the
entity families this task's already-implemented phases (P1's engine, P2's
migration of the existing register/mapping-store/review-queue) actually
populate get a full dataclass + repository methods here. The remaining
design-table families (``obligation_atoms``, ``internal_controls``,
``claims``/``findings``, ``policy_decisions``/``change_scenarios``/
``work_items``, ``entity_profiles``/``scope_revisions``) get their SCHEMA
now (so P3-P7 do not need another migration to introduce them) but are
intentionally left unpopulated — P2's job is the store, not the domain
logic that will fill these in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── source documents / revisions / sections / spans ─────────────────────────


@dataclass
class SourceDocument:
    """A stable LOGICAL document identity. Filenames/paths that alias to it
    change over time; this id never does."""

    logical_id: str
    title: str
    issuer: str
    source_kind: str  # regulatory_standard | implementation_plan | ... | unknown (design §3.1)
    jurisdiction: str
    org_id: str = "default"


@dataclass
class DocumentRevision:
    """Immutable bytes, keyed by full content hash. Re-ingesting identical
    bytes at any path is idempotent (same ``revision_id``); replacement bytes
    at the same alias path create a NEW revision — the old one, and every
    anchor into it, still resolves."""

    revision_id: str  # sha256 hex of the raw bytes
    logical_id: str
    alias_path: str  # the filename/path this revision was ingested from (an alias, not identity)
    binding_effect: str  # regulatory | internally_mandatory | advisory | descriptive | unknown
    authored_date: str | None = None
    approved_date: str | None = None
    effective_date: str | None = None
    last_reviewed_date: str | None = None
    retrieved_at: str = ""
    org_id: str = "default"
    recorded_from: str = ""
    recorded_to: str | None = None


@dataclass
class SourceSection:
    section_id: str
    revision_id: str
    path: str  # e.g. "R1 Part 1.2.6" or a heading path
    page_start: int | None = None
    page_end: int | None = None
    table_ref: str | None = None
    extractor: str = ""
    extractor_version: str = ""
    org_id: str = "default"


@dataclass
class SourceSpan:
    span_id: str
    section_id: str
    char_start: int
    char_end: int
    text_sha256: str
    org_id: str = "default"


# ── relationship assertions (proposal/effective separation, P2 core) ───────


@dataclass
class RelationshipAssertion:
    """Typed many-to-many edge with versioned endpoints. ``status`` is the
    proposal/effective boundary: normal governed reads filter to
    ``approved``; ``proposed``/``rejected``/``revoked``/``stale`` are only
    visible through the explicit candidate-discovery interface
    (``Repository.list_relationship_assertions`` with an explicit
    ``statuses`` argument) — a caller that forgets the filter gets nothing,
    never a silent proposal-as-fact leak."""

    assertion_id: str
    relation_type: str  # IMPLEMENTS | REFERENCES | EVIDENCES | ... (design §4)
    src_ref: str
    src_revision_id: str | None
    dst_ref: str
    dst_revision_id: str | None
    scope: str
    citations: list[dict] = field(default_factory=list)
    status: str = "proposed"  # proposed | approved | rejected | revoked | stale
    review_state: str = "proposed"
    valid_from: str | None = None
    valid_to: str | None = None
    recorded_from: str = ""
    recorded_to: str | None = None
    rationale: str = ""
    decided_by: str = ""
    decided_at: str | None = None
    version: int = 1  # optimistic concurrency token
    org_id: str = "default"
    # migration 5 (TASK_COMPLIANCE_STORE_CONSOLIDATION_V1): a requirement<->
    # document edge's coverage verdict. Empty string for edges that carry no
    # coverage judgement (e.g. a pure CROSS_REFERENCES structural edge).
    coverage: str = ""  # FULL | PARTIAL | NONE | NOT_APPLICABLE | NEEDS_REVIEW | ""
    proposed_coverage: str = ""  # what the system proposed — feeds the SME override rate
    confidence: float = 0.0


@dataclass
class ReviewEvent:
    """Transactional, append-only. A decision references its
    ``expected_version`` of the target; a stale expected version is rejected
    rather than silently overwriting a concurrent decision."""

    event_id: str
    target_type: str  # "relationship_assertion" | ...
    target_id: str
    expected_version: int
    decision: str  # CONFIRMED | CORRECTED | REJECTED | REVOKED
    decided_by: str
    rationale: str = ""
    evidence: list[dict] = field(default_factory=list)
    created_at: str = ""
    prior_event_id: str = ""
    org_id: str = "default"


@dataclass
class OutboxEvent:
    """Durable invalidation/index-publication event. A reader pins one
    consistent generation; an outbox row is how a downstream projection
    learns it must rebuild without polling every table."""

    event_id: int
    event_type: str
    payload: dict
    created_at: str
    published_at: str | None = None


@dataclass
class CatalogSnapshot:
    snapshot_id: str
    taken_at: str
    counts: dict
    hashes: dict
    org_id: str = "default"
