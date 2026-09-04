"""The review queue (TASK_COMPLIANCE_ENGINE_LANDING_V1 P1).

One mechanism replacing four would-be gates. An open item **never blocks
execution** — the system proceeds on its best evidence-backed answer and every
output derived from an open item names it. A decision is reversible: a
correction writes a **new row** that supersedes the prior one via
``prior_item_id``; the prior row is closed to ``SUPERSEDED``, never overwritten
or deleted — the same append-only discipline as the mapping store's
``valid_to`` closure, so the decision history stays replayable for an auditor.

Backed by LanceDB in the ``compliance_`` namespace (``compliance_review_queue``
table), via the shared retrieval store stage — no vectors, structured rows
only. ``proposed_value`` and ``evidence`` are stored as JSON text (the schema
is heterogeneous across ``kind``, see the module docstring's table in the task).
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field

_ID_RE = re.compile(r"[0-9a-f]{12}")  # matches uuid.uuid4().hex[:12] below

KINDS = (
    "applicability_scope",
    "document_tier",
    "compliance_conflict",
    "mapping_proposal",
    "low_confidence_extraction",
)
STATUSES = ("OPEN", "CONFIRMED", "REJECTED", "SUPERSEDED")

_TABLE = "review_queue"  # -> "compliance_review_queue" via the store prefix


@dataclass
class ReviewItem:
    kind: str
    subject_id: str
    proposed_value: dict
    evidence: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "OPEN"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    decided_by: str = ""
    decided_at: str = ""
    prior_item_id: str = ""
    created_at: float = field(default_factory=time.time)

    def to_row(self) -> dict:
        d = asdict(self)
        d["proposed_value"] = json.dumps(d["proposed_value"], sort_keys=True)
        d["evidence"] = json.dumps(d["evidence"], sort_keys=True)
        return d

    @classmethod
    def from_row(cls, row: dict) -> ReviewItem:
        r = dict(row)
        r["proposed_value"] = json.loads(r.get("proposed_value") or "{}")
        r["evidence"] = json.loads(r.get("evidence") or "[]")
        return cls(**{k: v for k, v in r.items() if k in cls.__dataclass_fields__})


def _schema():
    import pyarrow as pa

    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("kind", pa.string()),
            pa.field("subject_id", pa.string()),
            pa.field("proposed_value", pa.string()),  # JSON
            pa.field("evidence", pa.string()),  # JSON list[dict]
            pa.field("confidence", pa.float64()),
            pa.field("status", pa.string()),
            pa.field("decided_by", pa.string()),
            pa.field("decided_at", pa.string()),
            pa.field("prior_item_id", pa.string()),
            pa.field("created_at", pa.float64()),
        ]
    )


def _table(create: bool = True):
    from portal.platform.retrieval import store as _store

    db = _store.get_db()
    name = f"compliance_{_TABLE}"
    if name in db.table_names():
        return db.open_table(name)
    if not create:
        return None
    return db.create_table(name, schema=_schema())


def propose(
    kind: str,
    subject_id: str,
    proposed_value: dict,
    evidence: list[dict] | None = None,
    confidence: float = 0.0,
) -> ReviewItem:
    """File an OPEN item. Never raises on a low confidence — a low-confidence
    guess is queued with its best value, not withheld (P1/P3: 'nothing defaults
    silently')."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    item = ReviewItem(
        kind=kind,
        subject_id=subject_id,
        proposed_value=proposed_value,
        evidence=evidence or [],
        confidence=confidence,
    )
    _table(create=True).add([item.to_row()])
    return item


def get(item_id: str) -> ReviewItem | None:
    tbl = _table(create=False)
    if tbl is None:
        return None
    df = tbl.to_pandas()
    hit = df[df["id"] == item_id]
    if hit.empty:
        return None
    return ReviewItem.from_row(hit.iloc[0].to_dict())


def list_items(kind: str | None = None, status: str | None = None) -> list[ReviewItem]:
    tbl = _table(create=False)
    if tbl is None:
        return []
    df = tbl.to_pandas()
    if kind:
        df = df[df["kind"] == kind]
    if status:
        df = df[df["status"] == status]
    return [ReviewItem.from_row(r) for r in df.to_dict("records")]


def open_items(kind: str | None = None) -> list[ReviewItem]:
    return list_items(kind=kind, status="OPEN")


def decide(
    item_id: str, decision: str, decided_by: str, corrected_value: dict | None = None
) -> ReviewItem:
    """Confirm or reject an OPEN item. Writes a NEW row (the decision) with
    ``prior_item_id`` pointing at the item just closed; the prior row's own
    status flips to ``SUPERSEDED`` in place — its value is never rewritten,
    only its status. A later re-decision (a reversal) does the same thing again
    against the CONFIRMED/REJECTED row, keeping the whole chain replayable."""
    if decision not in ("CONFIRMED", "REJECTED"):
        raise ValueError("decision must be CONFIRMED or REJECTED")
    if not _ID_RE.fullmatch(item_id):
        # item_id reaches here from the compliance_review_decide MCP tool —
        # arbitrary model/user input — before an f-string filter below;
        # reject anything that isn't the id shape this module itself mints.
        raise ValueError(f"not a valid review-item id: {item_id!r}")
    prior = get(item_id)
    if prior is None:
        raise KeyError(item_id)
    tbl = _table(create=True)
    tbl.delete(f"id = '{item_id}'")
    tbl.add([{**prior.to_row(), "status": "SUPERSEDED"}])
    new_item = ReviewItem(
        kind=prior.kind,
        subject_id=prior.subject_id,
        proposed_value=corrected_value if corrected_value is not None else prior.proposed_value,
        evidence=prior.evidence,
        confidence=prior.confidence,
        status=decision,
        decided_by=decided_by,
        decided_at=time.strftime("%Y-%m-%d"),
        prior_item_id=item_id,
    )
    tbl.add([new_item.to_row()])
    return new_item


def sync_proposed_mappings(store) -> int:
    """Wire ``mapping_store``'s unapproved proposals (``approved_by == ""``)
    into the queue rather than a parallel proposal path (anti-pattern list).
    Idempotent: skips a mapping that already has an OPEN ``mapping_proposal``
    item. Returns the number of new queue items filed."""
    existing = {i.subject_id for i in open_items(kind="mapping_proposal")}
    n = 0
    for m in store._rows:  # noqa: SLF001 - MappingStore exposes no public iterator
        if m.is_approved or m.id in existing:
            continue
        propose(
            "mapping_proposal",
            subject_id=m.id,
            proposed_value={
                "requirement_id": m.requirement_id,
                "internal_document_id": m.internal_document_id,
                "section_id": m.section_id,
                "coverage": m.coverage,
                "relationship": m.relationship,
            },
            evidence=[
                {
                    "document": m.internal_document_id,
                    "section": m.section_id,
                    "page": None,
                    "span": "",
                }
            ],
            confidence=m.confidence,
        )
        n += 1
    return n
