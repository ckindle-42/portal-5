"""Evidence Record — the atomic evidence unit for investigations.

Phase 6a of BUILD_PROGRAM_SEC_RBP_V1.  V3 §2.3 / Edit E4.

Every tool call produces one EvidenceRecord with source_authority +
provenance + supports/contradicts links.  Evidence is immutable and
append-only — it doesn't get "promoted," it IS truth.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum


class SourceAuthority(str, Enum):  # noqa: UP042
    """How trustworthy is the source itself?"""

    AUTHORITATIVE_STRUCTURED = (
        "authoritative_structured"  # ATT&CK STIX, NVD, git-committed detections
    )
    AUTHORITATIVE_LIVE = "authoritative_live"  # Splunk field query, AD LDAP read
    ANNOTATED = "annotated"  # analyst notes
    REFERENCE = "reference"  # long-form docs
    EXTERNAL_UNVERIFIED = "external_unverified"  # RAG hits from vendor writeups


class EvidenceKind(str, Enum):  # noqa: UP042
    """What kind of evidence is this?"""

    SIEM_HIT = "siem_hit"
    EDR_PROCESS = "edr_process"
    AD_EVENT = "ad_event"
    DNS_RECORD = "dns_record"
    FILE_HASH = "file_hash"
    PCAP_FLOW = "pcap_flow"
    TI_REPORT = "ti_report"
    ANALYST_NOTE = "analyst_note"
    TOOL_OUTPUT = "tool_output"


def new_evidence_id() -> str:
    """Generate a unique evidence ID."""
    now = datetime.now(UTC)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    h = hashlib.sha256(f"{ts}{time.monotonic_ns()}".encode()).hexdigest()[:8]
    return f"ev-{ts}-{h}"


@dataclass
class EvidenceRecord:
    """The atomic evidence unit.  Every tool call produces one.

    Immutable and append-only — evidence IS truth, doesn't get "promoted."
    Symmetric with the truth-plane rule: the model never emits a verdict;
    the evaluator does.  The Reporter never emits a fact; the evidence store
    does.
    """

    evidence_id: str  # ev-YYYYMMDDTHHMMSSZ-<hash>
    episode_id: str  # links to Episode (from Phase 0+1)
    case_id: str  # links to investigation case (may be empty for pure R/B/P runs)
    kind: str  # EvidenceKind value
    source: dict  # {system, tool_invocation: {tool, arguments, trace_id}}
    timestamp: dict  # {collected_at, event_time}
    artifact: dict  # {identifiers: [], content_ref, content_hash, parse_schema_version}
    supports: list[str]  # hypothesis IDs this evidence supports
    contradicts: list[str]  # hypothesis IDs this evidence weakens
    confidence: dict  # {source_authority, parse_confidence}
    provenance: dict  # {collected_by_agent, chain_of_custody: []}

    def to_dict(self) -> dict:
        """JSON-safe dict for storage."""
        return asdict(self)

    def to_json(self) -> str:
        """JSON string for serialization."""
        return json.dumps(self.to_dict(), indent=2)


# ── Source authority helpers ──────────────────────────────────────────────────


def classify_source_authority(system: str) -> str:
    """Classify a source system's authority level.

    Returns a SourceAuthority string.
    """
    authority_map = {
        "splunk": SourceAuthority.AUTHORITATIVE_LIVE.value,
        "winevent": SourceAuthority.AUTHORITATIVE_LIVE.value,
        "wazuh": SourceAuthority.AUTHORITATIVE_LIVE.value,
        "crowdstrike": SourceAuthority.AUTHORITATIVE_LIVE.value,
        "ad": SourceAuthority.AUTHORITATIVE_LIVE.value,
        "atomic-red-team": SourceAuthority.AUTHORITATIVE_STRUCTURED.value,
        "mitre": SourceAuthority.AUTHORITATIVE_STRUCTURED.value,
        "nvd": SourceAuthority.AUTHORITATIVE_STRUCTURED.value,
        "virustotal": SourceAuthority.EXTERNAL_UNVERIFIED.value,
        "tenable": SourceAuthority.ANNOTATED.value,
    }
    return authority_map.get(system, SourceAuthority.EXTERNAL_UNVERIFIED.value)


# ── Evidence store ───────────────────────────────────────────────────────────


class EvidenceStore:
    """In-memory evidence store for one investigation case.

    Evidence is append-only and immutable.  Agents can query by ID, by
    hypothesis support/contradiction, or by kind.
    """

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    def add(self, record: EvidenceRecord) -> None:
        """Add an evidence record.  Overwrites if same ID (idempotent)."""
        self._records[record.evidence_id] = record

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        """Get an evidence record by ID."""
        return self._records.get(evidence_id)

    def list_all(self) -> list[EvidenceRecord]:
        """List all evidence records."""
        return list(self._records.values())

    def for_hypothesis(self, hypothesis_id: str) -> list[EvidenceRecord]:
        """Find evidence that supports or contradicts a hypothesis."""
        return [
            r
            for r in self._records.values()
            if hypothesis_id in r.supports or hypothesis_id in r.contradicts
        ]

    def supporting(self, hypothesis_id: str) -> list[EvidenceRecord]:
        """Find evidence that supports a hypothesis."""
        return [r for r in self._records.values() if hypothesis_id in r.supports]

    def contradicting(self, hypothesis_id: str) -> list[EvidenceRecord]:
        """Find evidence that contradicts a hypothesis."""
        return [r for r in self._records.values() if hypothesis_id in r.contradicts]

    def by_kind(self, kind: str) -> list[EvidenceRecord]:
        """Find evidence by kind."""
        return [r for r in self._records.values() if r.kind == kind]

    def count(self) -> int:
        return len(self._records)

    def to_dict(self) -> dict:
        return {
            "count": self.count(),
            "records": {k: v.to_dict() for k, v in self._records.items()},
        }
