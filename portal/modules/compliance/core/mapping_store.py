"""The mapping store (T3 Phase 4).

The system **proposes** `requirement -> document/section`; an SME **approves**.
Approved rows are consulted before retrieval and are **authoritative over model
judgement**. Every approved or corrected mapping is a labelled example, so the
evaluation set grows as a by-product of normal use instead of needing a separate
annotation campaign — the **SME override rate** is the trust signal.

Backed by JSON at ``COMPLIANCE_MAPPING_STORE`` (default
``data/compliance_mappings.json``). The committed file is empty — mappings point
at the *operator's* internal documents and never leave their machine.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"
STORE_PATH = Path(os.environ.get("COMPLIANCE_MAPPING_STORE", _DATA / "compliance_mappings.json"))

COVERAGE_VALUES = ("FULL", "PARTIAL", "NONE", "NOT_APPLICABLE", "NEEDS_REVIEW")


@dataclass
class Mapping:
    requirement_id: str  # "CIP-007-6 R2 Part 2.2"
    internal_document_id: str
    section_id: str
    relationship: str  # "implements" | "evidences" | "references"
    coverage: str  # one of COVERAGE_VALUES
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    approved_by: str = ""  # "" == proposed, not yet authoritative
    approved_date: str = ""
    confidence: float = 0.0
    source: str = "proposed"  # "proposed" | "sme" | "sme_correction"
    valid_from: str | None = None
    valid_to: str | None = None
    proposed_coverage: str = ""  # what the system proposed, kept for override-rate
    recorded_at: float = 0.0

    @property
    def is_approved(self) -> bool:
        return bool(self.approved_by)


class MappingStore:
    def __init__(self, path: Path | str = STORE_PATH):
        self.path = Path(path)
        self._rows: list[Mapping] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._rows = [Mapping(**r) for r in data.get("mappings", [])]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"mappings": [asdict(m) for m in self._rows]}, indent=1),
            encoding="utf-8",
        )

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
    ) -> Mapping:
        if coverage not in COVERAGE_VALUES:
            raise ValueError(f"coverage must be one of {COVERAGE_VALUES}")
        m = Mapping(
            requirement_id=requirement_id,
            internal_document_id=internal_document_id,
            section_id=section_id,
            relationship=relationship,
            coverage=coverage,
            proposed_coverage=coverage,
            confidence=confidence,
            source="proposed",
            valid_from=valid_from,
            recorded_at=time.time(),
        )
        self._rows.append(m)
        self._save()
        return m

    def approve(self, mapping_id: str, sme: str, coverage: str | None = None) -> Mapping:
        """SME sign-off. If ``coverage`` is given and differs from what the
        system proposed, it is recorded as an override (feeds the override rate
        and the labelled eval set)."""
        m = self._by_id(mapping_id)
        if coverage is not None:
            if coverage not in COVERAGE_VALUES:
                raise ValueError(f"coverage must be one of {COVERAGE_VALUES}")
            m.coverage = coverage
        m.approved_by = sme
        m.approved_date = time.strftime("%Y-%m-%d")
        m.source = "sme_correction" if m.coverage != m.proposed_coverage else "sme"
        self._save()
        return m

    def revoke(self, mapping_id: str, sme: str) -> Mapping:
        """Reverse a prior approval (F09/P1.3): a later rejection/reversal must
        actually revoke a previously-approved mapping, not just record a
        review-queue decision that the effective mapping never sees. Clearing
        ``approved_by`` immediately removes this row from ``approved_for`` —
        the row itself is kept (never deleted) so its history is auditable."""
        m = self._by_id(mapping_id)
        m.approved_by = ""
        m.approved_date = ""
        m.source = "revoked"
        self._save()
        return m

    def _by_id(self, mapping_id: str) -> Mapping:
        for m in self._rows:
            if m.id == mapping_id:
                return m
        raise KeyError(mapping_id)

    # ── lookup ───────────────────────────────────────────────────────────────
    def approved_for(self, requirement_id: str, effective_on: str | None = None) -> list[Mapping]:
        """Approved rows for a requirement, valid on ``effective_on`` (ISO date).
        These short-circuit retrieval and are authoritative over model judgement."""
        out = []
        for m in self._rows:
            if m.requirement_id != requirement_id or not m.is_approved:
                continue
            if effective_on:
                if m.valid_from and m.valid_from > effective_on:
                    continue
                if m.valid_to and m.valid_to <= effective_on:
                    continue
            out.append(m)
        return out

    def all_for(self, requirement_id: str) -> list[Mapping]:
        return [m for m in self._rows if m.requirement_id == requirement_id]

    # ── trust signal ─────────────────────────────────────────────────────────
    def override_rate(self) -> dict:
        approved = [m for m in self._rows if m.is_approved]
        overrides = [m for m in approved if m.source == "sme_correction"]
        return {
            "n_proposed": len(self._rows),
            "n_approved": len(approved),
            "n_sme_overrides": len(overrides),
            "override_rate": (len(overrides) / len(approved)) if approved else None,
            "labelled_examples": len(approved),  # the eval set, grown as a by-product
        }

    def __len__(self) -> int:
        return len(self._rows)
