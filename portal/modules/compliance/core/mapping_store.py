"""The mapping store (T3 Phase 4) — a ``Repository``-backed facade
(TASK_COMPLIANCE_STORE_CONSOLIDATION_V1).

The system **proposes** `requirement -> document/section`; an SME **approves**.
Approved rows are consulted before retrieval and are **authoritative over model
judgement**. Every approved or corrected mapping is a labelled example, so the
evaluation set grows as a by-product of normal use instead of needing a separate
annotation campaign — the **SME override rate** is the trust signal.

A requirement<->document coverage judgement IS a relationship_assertions row
(schema migration 5 added ``coverage``/``proposed_coverage``/``confidence``
columns) — the same edge ``compliance_trace`` already traverses, not a second
data model living in a parallel JSON file. This module keeps the ``Mapping``
dataclass and every public method's signature stable; only the storage
backend changed, so ``coverage.py``, ``change_pipeline.py``, and
``compliance_mcp.py`` needed no changes to their calling convention.

Backed by SQLite at ``COMPLIANCE_MAPPING_STORE`` (default: the same
``compliance_store.db`` every other canonical-store reader uses — passing a
different path, as every existing test does with a throwaway ``tmp_path``,
still gets full isolation, since a distinct file is a distinct store).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from portal.modules.compliance.core.models import RelationshipAssertion
from portal.modules.compliance.core.repository import Repository

_DATA = Path(__file__).resolve().parent.parent / "data"
STORE_PATH = Path(os.environ.get("COMPLIANCE_MAPPING_STORE", str(_DATA / "compliance_store.db")))

COVERAGE_VALUES = ("FULL", "PARTIAL", "NONE", "NOT_APPLICABLE", "NEEDS_REVIEW")

# Only these relation types are this facade's own — a future typed edge
# (e.g. CROSS_REFERENCES between two requirement nodes) must never be
# silently surfaced as a requirement<->document coverage mapping.
_MAPPING_RELATION_TYPES = ("IMPLEMENTS", "EVIDENCES", "REFERENCES")
_ALL_STATUSES = ("proposed", "approved", "rejected", "revoked", "stale")
_SEP = "::"  # dst_ref = f"{internal_document_id}{_SEP}{section_id}"


@dataclass
class Mapping:
    requirement_id: str  # "CIP-007-6 R2 Part 2.2"
    internal_document_id: str
    section_id: str
    relationship: str  # "implements" | "evidences" | "references"
    coverage: str  # one of COVERAGE_VALUES
    id: str = ""
    approved_by: str = ""  # "" == proposed, not yet authoritative
    approved_date: str = ""
    confidence: float = 0.0
    source: str = "proposed"  # "proposed" | "sme" | "sme_correction" | "revoked" | ...
    valid_from: str | None = None
    valid_to: str | None = None
    proposed_coverage: str = ""  # what the system proposed, kept for override-rate
    recorded_at: float = 0.0

    @property
    def is_approved(self) -> bool:
        return bool(self.approved_by)


def _split_dst(dst_ref: str) -> tuple[str, str]:
    doc_id, sep, section_id = dst_ref.partition(_SEP)
    return doc_id, section_id if sep else ""


def _relationship_to_mapping(rel: RelationshipAssertion) -> Mapping:
    doc_id, section_id = _split_dst(rel.dst_ref)
    if rel.status == "approved":
        source = "sme_correction" if rel.review_state == "CORRECTED" else "sme"
        approved_by = rel.decided_by
        approved_date = (rel.decided_at or "")[:10]
    elif rel.status in ("revoked", "rejected"):
        source = rel.status
        approved_by = ""
        approved_date = ""
    else:  # proposed / stale — review_state carries a free-text creation-time
        # marker (e.g. "successor_of_expired") when it isn't the plain default.
        source = rel.review_state if rel.review_state != "proposed" else "proposed"
        approved_by = ""
        approved_date = ""
    recorded_at = 0.0
    if rel.recorded_from:
        try:
            recorded_at = datetime.fromisoformat(rel.recorded_from).timestamp()
        except ValueError:
            recorded_at = 0.0
    return Mapping(
        requirement_id=rel.src_ref,
        internal_document_id=doc_id,
        section_id=section_id,
        relationship=rel.relation_type.lower(),
        coverage=rel.coverage,
        id=rel.assertion_id,
        approved_by=approved_by,
        approved_date=approved_date,
        confidence=rel.confidence,
        source=source,
        valid_from=rel.valid_from,
        valid_to=rel.valid_to,
        proposed_coverage=rel.proposed_coverage,
        recorded_at=recorded_at,
    )


class MappingStore:
    def __init__(self, path: Path | str = STORE_PATH):
        self.path = Path(path)
        self._repo = Repository(self.path)

    # ── propose / approve ────────────────────────────────────────────────────
    def propose(
        self,
        requirement_id: str,
        internal_document_id: str,
        section_id: str,
        coverage: str,
        *,
        relationship: str = "implements",
        confidence: float = 0.0,
        valid_from: str | None = None,
        source: str = "proposed",
    ) -> Mapping:
        if coverage not in COVERAGE_VALUES:
            raise ValueError(f"coverage must be one of {COVERAGE_VALUES}")
        rel = RelationshipAssertion(
            assertion_id="",
            relation_type=relationship.upper(),
            src_ref=requirement_id,
            src_revision_id=None,
            dst_ref=f"{internal_document_id}{_SEP}{section_id}",
            dst_revision_id=None,
            scope="",
            citations=[],
            status="proposed",
            review_state=source,
            valid_from=valid_from,
            coverage=coverage,
            proposed_coverage=coverage,
            confidence=confidence,
        )
        saved = self._repo.propose_relationship(rel)
        return _relationship_to_mapping(saved)

    def approve(self, mapping_id: str, sme: str, coverage: str | None = None) -> Mapping:
        """SME sign-off. If ``coverage`` is given and differs from what the
        system proposed, it is recorded as an override (feeds the override rate
        and the labelled eval set)."""
        current = self._repo.get_relationship(mapping_id)
        if current is None:
            raise KeyError(mapping_id)
        if coverage is not None and coverage not in COVERAGE_VALUES:
            raise ValueError(f"coverage must be one of {COVERAGE_VALUES}")
        is_correction = coverage is not None and coverage != current.coverage
        updated = self._repo.decide_relationship(
            mapping_id,
            "CORRECTED" if is_correction else "CONFIRMED",
            sme,
            expected_version=current.version,
            corrected_coverage=coverage if is_correction else None,
        )
        return _relationship_to_mapping(updated)

    def revoke(self, mapping_id: str, sme: str) -> Mapping:
        """Reverse a prior approval (F09/P1.3): a later rejection/reversal must
        actually revoke a previously-approved mapping, not just record a
        review-queue decision that the effective mapping never sees. The row
        itself is kept (never deleted) so its history is auditable."""
        current = self._repo.get_relationship(mapping_id)
        if current is None:
            raise KeyError(mapping_id)
        updated = self._repo.decide_relationship(
            mapping_id, "REVOKED", sme, expected_version=current.version
        )
        return _relationship_to_mapping(updated)

    def close_validity(self, mapping_id: str, valid_to: str) -> Mapping:
        """Close ``valid_to`` because the STANDARD superseded this mapping's
        target Part, not because an SME reviewed and rejected it — no review
        event, approval status untouched (P4's ``expire_mappings``)."""
        return _relationship_to_mapping(
            self._repo.close_relationship_validity(mapping_id, valid_to)
        )

    def _by_id(self, mapping_id: str) -> Mapping:
        rel = self._repo.get_relationship(mapping_id)
        if rel is None:
            raise KeyError(mapping_id)
        return _relationship_to_mapping(rel)

    # ── lookup ───────────────────────────────────────────────────────────────
    def approved_for(self, requirement_id: str, effective_on: str | None = None) -> list[Mapping]:
        """Approved rows for a requirement, valid on ``effective_on`` (ISO date).
        These short-circuit retrieval and are authoritative over model judgement."""
        out = []
        for rel in self._repo.list_relationship_assertions(
            ref=requirement_id, statuses=("approved",)
        ):
            if rel.relation_type not in _MAPPING_RELATION_TYPES or rel.src_ref != requirement_id:
                continue
            if effective_on:
                if rel.valid_from and rel.valid_from > effective_on:
                    continue
                if rel.valid_to and rel.valid_to <= effective_on:
                    continue
            out.append(_relationship_to_mapping(rel))
        return out

    def all_for(self, requirement_id: str) -> list[Mapping]:
        return [
            _relationship_to_mapping(rel)
            for rel in self._repo.list_relationship_assertions(
                ref=requirement_id, statuses=_ALL_STATUSES
            )
            if rel.relation_type in _MAPPING_RELATION_TYPES and rel.src_ref == requirement_id
        ]

    @property
    def _rows(self) -> list[Mapping]:
        return [
            _relationship_to_mapping(rel)
            for rel in self._repo.list_relationship_assertions(statuses=_ALL_STATUSES)
            if rel.relation_type in _MAPPING_RELATION_TYPES
        ]

    # ── trust signal ─────────────────────────────────────────────────────────
    def override_rate(self) -> dict:
        rows = self._rows
        approved = [m for m in rows if m.is_approved]
        overrides = [m for m in approved if m.source == "sme_correction"]
        return {
            "n_proposed": len(rows),
            "n_approved": len(approved),
            "n_sme_overrides": len(overrides),
            "override_rate": (len(overrides) / len(approved)) if approved else None,
            "labelled_examples": len(approved),  # the eval set, grown as a by-product
        }

    def __len__(self) -> int:
        return len(self._rows)
