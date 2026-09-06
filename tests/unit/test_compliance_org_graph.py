"""P2 organization-graph extraction discipline (TASK_COMPLIANCE_REASONING_V6).

No network, no real PDFs — a synthetic controlled-procedure markdown stands in
for docling output so the structure/span/fidelity logic is exercised in CI.
The real 68-PDF corpus build is a private-data step run outside the repo.
"""

from __future__ import annotations

from portal.modules.compliance.core.org_graph import (
    _iso,
    extract_section_nodes,
    parse_control_block,
    parse_sections,
)

_DOC = """<!-- image -->

## LSPG Security Patch Management Procedure

Effective Date:  July 31, 2026

Document Type: Procedure

NERC Standard: CIP-007

Document Number:  LSPG-ADM-CIP007SPM

| APPROVALS | APPROVALS |
|-----------|-----------|
| Name: Richard Morgan | 7/24/2026 |

| DOCUMENTOWNER | DOCUMENTOWNER |
|---------------|---------------|
| Ryan Borg | Manager of OT Security Operations |

## 1.0 Introduction

## 1.2 Applicability

This procedure applies to all high and medium impact BES Cyber Systems.

## 3.1 Security Patch Management Process

The OT Security Team shall evaluate security patches for applicability at least once every 35 calendar days. The System Owner reviews the patch register monthly and documents the results in the evidence log.

## 5.1 Appendix 1: Requirements Traceability

Per CIP-007-6 R2 Part 2.2, the Responsible Entity shall evaluate security patches for applicability every 35 days.
"""


def test_iso_date_parsing():
    assert _iso("July 31, 2026") == "2026-07-31"
    assert _iso("7/24/2026") == "2026-07-24"
    assert _iso("garbage") == ""


def test_control_block_reads_document_not_filename():
    cb = parse_control_block(_DOC)
    assert cb["effective_date"] == "2026-07-31"
    assert cb["nerc_standard"] == "CIP-007"
    assert cb["document_number"] == "LSPG-ADM-CIP007SPM"
    assert cb.get("owner") == "Ryan Borg"
    assert "effective_date" in cb["found"] and "nerc_standard" in cb["found"]


def test_sections_are_document_declared_and_spanned():
    secs = parse_sections(_DOC, "spm")
    numbered = [s for s in secs if s.number]
    assert {s.number for s in numbered} == {"1.0", "1.2", "3.1", "5.1"}
    for s in secs:
        assert _DOC[s.char_start : s.char_end].startswith("#")


def test_extracted_nodes_round_trip_verbatim():
    secs = parse_sections(_DOC, "spm")
    proc = next(s for s in secs if s.number == "3.1")
    body = _DOC[proc.char_start : proc.char_end]
    nodes = extract_section_nodes(proc, body, is_traceability=False)
    assert nodes
    for n in nodes:
        assert _DOC[n.char_start : n.char_end] == n.text
    kinds = {n.node_type for n in nodes}
    assert "commitment" in kinds or "activity" in kinds
    # the 35-calendar-day cadence sentence is picked up as an activity
    assert any("35 calendar days" in n.text for n in nodes)


def test_definitional_section_becomes_a_premise():
    secs = parse_sections(_DOC, "spm")
    appl = next(s for s in secs if s.number == "1.2")
    body = _DOC[appl.char_start : appl.char_end]
    nodes = extract_section_nodes(appl, body, is_traceability=False)
    assert nodes and nodes[0].node_type == "premise"
    assert _DOC[nodes[0].char_start : nodes[0].char_end] == nodes[0].text


def test_traceability_section_is_references_not_implements():
    secs = parse_sections(_DOC, "spm")
    trace = next(s for s in secs if s.number == "5.1")
    body = _DOC[trace.char_start : trace.char_end]
    nodes = extract_section_nodes(trace, body, is_traceability=True)
    assert nodes
    assert all(n.fields.get("relation") == "REFERENCES" for n in nodes if "relation" in n.fields)
