"""Auditable corpus-boundary receipts for absence determinations.

An absence claim ("we read the corpus to its declared boundary and nothing
addresses this obligation") is only as good as the boundary it rests on. A
search that *ran* is not a search that *read the declared population*: the
receipt below records which documents/sections were eligible, which were
actually examined, which candidates were rejected and why, and any known
omission. ``BoundarySearch.exhaustive`` requires it, so a legacy query-list +
manifest proof can no longer certify a new-engine absence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portal.modules.compliance.core.repository import Repository

#: acquisition modes for a completed boundary receipt.
_BOUNDARY_MODES = ("RETRIEVAL", "EXPLICIT_SET")


@dataclass(frozen=True)
class BoundaryCompletenessReceipt:
    """Proof that the declared population was accounted for, section by section.

    ``eligible`` lists the document/section identities the boundary claimed to
    cover (each with an optional ``revision_hash``); ``examined`` lists the
    identities actually read; ``rejected`` records candidate rejection links and
    their reasons; ``omissions`` lists known-unexamined identities. A receipt is
    complete only when every eligible identity is examined or explicitly
    rejected, with no omissions.
    """

    eligible: list[dict[str, Any]] = field(default_factory=list)
    examined: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    omissions: list[str] = field(default_factory=list)
    acquisition_mode: str = "RETRIEVAL"
    revision_hashes: dict[str, str] = field(default_factory=dict)

    def _identity(self, entry: dict[str, Any]) -> str:
        return str(entry.get("section_id") or entry.get("document_id") or entry.get("ref") or "")

    def accounted(self) -> set[str]:
        return (
            set(self.examined)
            | {str(r.get("ref", "")) for r in self.rejected}
            | set(self.omissions)
        )

    def unaccounted(self) -> list[str]:
        """Eligible identities neither examined nor explicitly rejected."""
        accounted = self.accounted()
        return sorted(
            identity
            for identity in (self._identity(entry) for entry in self.eligible)
            if identity and identity not in accounted
        )

    @property
    def complete(self) -> bool:
        return (
            bool(self.eligible)
            and not self.omissions
            and not self.unaccounted()
            and self.acquisition_mode in _BOUNDARY_MODES
        )


@dataclass(frozen=True)
class BoundarySearch:
    subject_ref: str
    queries: list[str]
    index_generation: str
    manifest_hash: str
    eligible_document_count: int
    retrieved: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    truncation_flags: list[str] = field(default_factory=list)
    budget_ceilings: dict[str, Any] = field(default_factory=dict)
    #: required for a new-engine absence claim; absent on legacy proofs.
    completeness_receipt: BoundaryCompletenessReceipt | None = None

    @property
    def exhaustive(self) -> bool:
        receipt = self.completeness_receipt
        if receipt is None or not receipt.complete:
            return False
        return bool(self.queries and self.index_generation) and not (
            self.truncation_flags or any(self.budget_ceilings.values())
        )

    @property
    def stable_id(self) -> str:
        body = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "boundary-" + hashlib.sha256(body.encode()).hexdigest()[:20]

    def to_dict(self) -> dict[str, Any]:
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
            "completeness_receipt": (
                asdict(self.completeness_receipt) if self.completeness_receipt else None
            ),
        }


def build_queries(
    requirement_id: str, atom: dict[str, Any], definitions: dict[str, str] | None = None
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


def persist(repo: Repository, search: BoundarySearch) -> str:
    """Persist an absence proof, refusing any boundary without a complete
    receipt. This is the gate ``Repository.record_boundary_proof`` cannot itself
    express against the frozen schema."""
    from portal.modules.compliance.core.runtime import bump

    bump("boundary")
    receipt = search.completeness_receipt
    if receipt is None or not receipt.complete:
        raise ValueError(
            "absence proof rejected: no completed-boundary receipt "
            "(eligible/examined sets or unexplained omissions)"
        )
    if not search.exhaustive:
        raise ValueError("incomplete retrieval cannot be persisted as an absence proof")
    eligible_count = len(receipt.eligible) or search.eligible_document_count
    return repo.record_boundary_proof(
        subject_ref=search.subject_ref,
        query_set=search.queries,
        index_generation=search.index_generation,
        manifest_hash=search.manifest_hash,
        eligible_document_count=eligible_count,
        candidates_retrieved=search.retrieved,
        candidates_rejected=search.rejected,
        truncation_flags=search.truncation_flags,
        budget_ceilings=search.budget_ceilings,
        boundary_proof_id=search.stable_id,
    )
