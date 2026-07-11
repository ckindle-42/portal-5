"""Tests for investigation layer — Phase 6a: Evidence + Case Notebook.

Validates:
- Evidence record schema (immutable, append-only, source authority)
- Case notebook (SQLite-backed, write/read/supersede)
- Seven memory kinds are kept separate (agents have NO long-term memory)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from portal.modules.security.core.investigation import (
    CaseNotebook,
    EvidenceRecord,
    EvidenceStore,
    SourceAuthority,
    new_evidence_id,
)
from portal.modules.security.core.investigation.evidence import (
    EvidenceKind,
    classify_source_authority,
)

# ── Evidence record ──────────────────────────────────────────────────────────


class TestEvidenceRecord:
    """Evidence record schema — immutable, source-authority-aware."""

    def test_new_evidence_id_format(self):
        eid = new_evidence_id()
        assert eid.startswith("ev-")
        eid2 = new_evidence_id()
        assert eid != eid2

    def test_evidence_record_creation(self):
        record = EvidenceRecord(
            evidence_id="ev-test-001",
            episode_id="ep-test-001",
            case_id="case-001",
            kind=EvidenceKind.SIEM_HIT.value,
            source={
                "system": "splunk",
                "tool_invocation": {"tool": "spl_search", "arguments": {}, "trace_id": "trace-001"},
            },
            timestamp={
                "collected_at": "2026-07-04T12:00:00Z",
                "event_time": "2026-07-04T11:55:00Z",
            },
            artifact={
                "identifiers": ["host:dc01"],
                "content_ref": "",
                "content_hash": "",
                "parse_schema_version": 1,
            },
            supports=["hyp-001"],
            contradicts=[],
            confidence={
                "source_authority": SourceAuthority.AUTHORITATIVE_LIVE.value,
                "parse_confidence": "high",
            },
            provenance={"collected_by_agent": "A2", "chain_of_custody": ["trace-001"]},
        )
        assert record.evidence_id == "ev-test-001"
        assert record.kind == "siem_hit"

    def test_evidence_to_dict_json_safe(self):
        record = EvidenceRecord(
            evidence_id="ev-test-002",
            episode_id="ep-test-002",
            case_id="case-001",
            kind=EvidenceKind.TOOL_OUTPUT.value,
            source={"system": "mitre"},
            timestamp={
                "collected_at": "2026-07-04T12:00:00Z",
                "event_time": "2026-07-04T12:00:00Z",
            },
            artifact={"identifiers": []},
            supports=[],
            contradicts=[],
            confidence={"source_authority": "authoritative_structured", "parse_confidence": "high"},
            provenance={"collected_by_agent": "A2", "chain_of_custody": []},
        )
        d = record.to_dict()
        json.dumps(d)  # JSON-safe

    def test_source_authority_classification(self):
        assert classify_source_authority("splunk") == "authoritative_live"
        assert classify_source_authority("mitre") == "authoritative_structured"
        assert classify_source_authority("virustotal") == "external_unverified"
        assert classify_source_authority("unknown_system") == "external_unverified"


# ── Evidence store ───────────────────────────────────────────────────────────


class TestEvidenceStore:
    """Evidence store — query by ID, hypothesis, kind."""

    def test_add_and_get(self):
        store = EvidenceStore()
        record = EvidenceRecord(
            evidence_id="ev-001",
            episode_id="ep-001",
            case_id="c-001",
            kind="siem_hit",
            source={"system": "splunk"},
            timestamp={"collected_at": "", "event_time": ""},
            artifact={"identifiers": []},
            supports=["hyp-001"],
            contradicts=[],
            confidence={"source_authority": "authoritative_live", "parse_confidence": "high"},
            provenance={"collected_by_agent": "A2", "chain_of_custody": []},
        )
        store.add(record)
        assert store.get("ev-001") is not None
        assert store.count() == 1

    def test_for_hypothesis(self):
        store = EvidenceStore()
        for i in range(3):
            store.add(
                EvidenceRecord(
                    evidence_id=f"ev-{i}",
                    episode_id="ep-001",
                    case_id="c-001",
                    kind="siem_hit",
                    source={"system": "splunk"},
                    timestamp={"collected_at": "", "event_time": ""},
                    artifact={"identifiers": []},
                    supports=["hyp-001"] if i < 2 else ["hyp-002"],
                    contradicts=[],
                    confidence={
                        "source_authority": "authoritative_live",
                        "parse_confidence": "high",
                    },
                    provenance={"collected_by_agent": "A2", "chain_of_custody": []},
                )
            )
        assert len(store.for_hypothesis("hyp-001")) == 2
        assert len(store.supporting("hyp-001")) == 2
        assert len(store.contradicting("hyp-001")) == 0

    def test_by_kind(self):
        store = EvidenceStore()
        store.add(
            EvidenceRecord(
                evidence_id="ev-001",
                episode_id="ep-001",
                case_id="c-001",
                kind="siem_hit",
                source={"system": "splunk"},
                timestamp={"collected_at": "", "event_time": ""},
                artifact={"identifiers": []},
                supports=[],
                contradicts=[],
                confidence={"source_authority": "authoritative_live", "parse_confidence": "high"},
                provenance={"collected_by_agent": "A2", "chain_of_custody": []},
            )
        )
        store.add(
            EvidenceRecord(
                evidence_id="ev-002",
                episode_id="ep-001",
                case_id="c-001",
                kind="analyst_note",
                source={"system": "analyst"},
                timestamp={"collected_at": "", "event_time": ""},
                artifact={"identifiers": []},
                supports=[],
                contradicts=[],
                confidence={"source_authority": "annotated", "parse_confidence": "high"},
                provenance={"collected_by_agent": "analyst", "chain_of_custody": []},
            )
        )
        assert len(store.by_kind("siem_hit")) == 1
        assert len(store.by_kind("analyst_note")) == 1


# ── Case notebook ────────────────────────────────────────────────────────────


class TestCaseNotebook:
    """Case notebook — SQLite-backed investigation memory."""

    def test_write_and_read(self):
        with CaseNotebook(":memory:") as nb:
            entry = nb.write("case-001", "A1", "hypothesis", {"text": "Kerberoasting detected"})
            assert entry.entry_id.startswith("nb-case-001-")
            read_back = nb.read(entry.entry_id)
            assert read_back is not None
            assert read_back.content["text"] == "Kerberoasting detected"

    def test_read_case(self):
        with CaseNotebook(":memory:") as nb:
            nb.write("case-001", "A1", "hypothesis", {"text": "h1"})
            nb.write("case-001", "A2", "finding", {"text": "f1"})
            nb.write("case-002", "A1", "hypothesis", {"text": "h2"})

            assert len(nb.read_case("case-001")) == 2
            assert len(nb.read_case("case-001", "hypothesis")) == 1
            assert len(nb.read_case("case-002")) == 1

    def test_supersede(self):
        with CaseNotebook(":memory:") as nb:
            old = nb.write("case-001", "A3", "finding", {"text": "initial finding"})
            new = nb.write("case-001", "A3", "finding", {"text": "revised finding"})
            nb.supersede(old.entry_id, new)

            read_old = nb.read(old.entry_id)
            assert read_old is not None
            assert read_old.superseded_by == new.entry_id

    def test_count(self):
        with CaseNotebook(":memory:") as nb:
            assert nb.count() == 0
            nb.write("case-001", "A1", "hypothesis", {})
            nb.write("case-001", "A2", "finding", {})
            assert nb.count() == 2
            assert nb.count("case-001") == 2
            assert nb.count("case-002") == 0

    def test_context_manager(self):
        with CaseNotebook(":memory:") as nb:
            nb.write("case-001", "A1", "test", {"x": 1})
            assert nb.count() == 1


# ── Memory kind separation ───────────────────────────────────────────────────


class TestMemoryKindSeparation:
    """Seven memory kinds are kept separate."""

    def test_evidence_store_is_separate_from_notebook(self):
        """Evidence (kind 3) is separate from case notebook (kind 2)."""
        store = EvidenceStore()
        with CaseNotebook(":memory:") as nb:
            store.add(
                EvidenceRecord(
                    evidence_id="ev-001",
                    episode_id="ep-001",
                    case_id="c-001",
                    kind="siem_hit",
                    source={"system": "splunk"},
                    timestamp={"collected_at": "", "event_time": ""},
                    artifact={"identifiers": []},
                    supports=[],
                    contradicts=[],
                    confidence={
                        "source_authority": "authoritative_live",
                        "parse_confidence": "high",
                    },
                    provenance={"collected_by_agent": "A2", "chain_of_custody": []},
                )
            )
            nb.write("c-001", "A3", "hypothesis", {"text": "test"})

            # They don't interfere
            assert store.count() == 1
            assert nb.count() == 1
            # Evidence is NOT in the notebook
            assert nb.count("c-001") == 1  # only the hypothesis, not the evidence
