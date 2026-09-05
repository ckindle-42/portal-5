"""Auditable corpus-boundary receipts for absence determinations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BoundarySearch:
    subject_ref: str
    queries: list[str]
    index_generation: str
    manifest_hash: str
    eligible_document_count: int
    retrieved: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    truncation_flags: list[str] = field(default_factory=list)
    budget_ceilings: dict = field(default_factory=dict)

    @property
    def exhaustive(self) -> bool:
        return bool(self.queries and self.index_generation) and not (
            self.truncation_flags or any(self.budget_ceilings.values())
        )

    @property
    def stable_id(self) -> str:
        body = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "boundary-" + hashlib.sha256(body.encode()).hexdigest()[:20]

    def to_dict(self) -> dict:
        return {
            "subject_ref": self.subject_ref,
            "query_set": self.queries,
            "index_generation": self.index_generation,
            "manifest_hash": self.manifest_hash,
            "eligible_document_count": self.eligible_document_count,
            "candidates_retrieved": self.retrieved,
            "candidates_rejected": self.rejected,
            "truncation_flags": self.truncation_flags,
            "budget_ceilings": self.budget_ceilings,
        }


def build_queries(
    requirement_id: str, atom: dict, definitions: dict[str, str] | None = None
) -> list[str]:
    """Build and retain every query family required by P4."""
    from portal.modules.compliance.core.runtime import bump

    bump("boundary")
    definitions = definitions or {}
    action = str(atom.get("action", "")).strip()
    obj = str(atom.get("object", "")).strip()
    expanded = " ".join(definitions.get(term, term) for term in obj.split())
    plain = " ".join(part for part in (action, expanded) if part)
    queries = [requirement_id, " ".join(part for part in (requirement_id, action, obj) if part)]
    if plain:
        queries.extend([plain, plain.replace("BES", "bulk electric system")])
    return list(dict.fromkeys(q for q in queries if q.strip()))


def persist(repo, search: BoundarySearch) -> str:
    from portal.modules.compliance.core.runtime import bump

    bump("boundary")
    if not search.exhaustive:
        raise ValueError("incomplete retrieval cannot be persisted as an absence proof")
    return repo.record_boundary_proof(
        subject_ref=search.subject_ref,
        query_set=search.queries,
        index_generation=search.index_generation,
        manifest_hash=search.manifest_hash,
        eligible_document_count=search.eligible_document_count,
        candidates_retrieved=search.retrieved,
        candidates_rejected=search.rejected,
        truncation_flags=search.truncation_flags,
        budget_ceilings=search.budget_ceilings,
        boundary_proof_id=search.stable_id,
    )
