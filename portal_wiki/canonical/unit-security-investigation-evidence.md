---
id: unit-security-investigation-evidence
kind: mixed
title: "Investigation evidence \u2014 immutable append-only evidence unit"
sources:
- type: code
  path: portal/modules/security/core/investigation/evidence.py
  commit: 573a2377
last_generated_commit: 573a2377
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- investigation
created_at: 1785796315.133636
updated_at: 1785796315.133636
---

`EvidenceRecord` is the atomic evidence unit for investigations: every tool
call during an engagement produces one record carrying its source authority,
its provenance, and its supports/contradicts links. Evidence is immutable and
append-only — it does not get promoted, it is truth.

## Why

The immutability discipline is the whole design. If an investigation could
revise or delete a piece of evidence, then a conclusion could quietly rest on
a record that no longer exists, and the audit trail — the thing that makes an
AI investigation trustworthy at all — would be a fiction. `SourceAuthority`
grades the source itself (authoritative structured data like ATT&CK STIX or
git-committed detections, live authoritative reads like a Splunk field query,
down to external unverified RAG hits) so a downstream decision can weight the
*trustworthiness of the source* separately from the content of the record.
The supports/contradicts links are what let the reasoning layer assemble an
argument instead of a pile of facts.

## Interfaces

`EvidenceRecord` is the dataclass with id, source authority, provenance, and
link fields; `EvidenceStore` is the append-only store; `SourceAuthority` and
`EvidenceKind` are the enums grading source trust and record type;
`new_evidence_id` generates the unique id.

## Gotchas

The authority ladder is deliberately coarse (five levels) — it is not a
score but a provenance class, so a low-authority record is never weighted as
if it were high merely because its *content* looks credible.
