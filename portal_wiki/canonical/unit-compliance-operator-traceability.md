---
id: unit-compliance-operator-traceability
kind: what
title: "Compliance operator traceability — the appendix as labelled assertions, never as read verification"
sources:
- type: code
  path: portal/modules/compliance/core/operator_traceability.py
claims: []
confidence: high
tags:
- compliance
- traceability
- ingest
created_at: 1760000000.0
updated_at: 1760000000.0
---

# Compliance operator traceability

Roughly half the operator's controlled documents end with a "Requirements
Traceability" appendix — the operator's OWN table mapping its sections to the
standard's requirements. `operator_traceability` promotes the D-DT-8 probe
parser into the internal corpus: each appendix row becomes two
machine_determined assertions in `relationship_assertions` under
`derivation='operator_traceability'` — document-level `ADDRESSES` (document →
requirement) and section-level `IMPLEMENTS` (requirement → section) — with the
appendix row itself recorded in `citations_json` and the rationale naming the
assertion as the operator's declaration, not read verification.

Requirement resolution is the probe's, unchanged: Part rows are confirmed by
text (≥0.6 word overlap of the row's restated requirement against the
governing-anchor normative text, the check that rejected the probe's 24 header
misreads); whole-requirement rows resolve structurally, currency-preferred.
Section resolution runs the probe's rules first (exact number, parent-prefix,
then a line-start scan for paragraphs folded inside another section's body);
undotted appendix numbers ("Section 3" stored as 3.0) fill only gaps the
probe's rules miss, and never displace a folded hit, because controlled
documents carry misnumbered duplicate runs (owner lists numbered 1.0–8.1) that
a `.0` equivalence happily matches while the operator meant the body section.

A revision's assertions are rebuilt idempotently — `record_traceability`
replaces exactly that revision's rows — and the internal-corpus materializer
calls it per document, so a new upload's appendix becomes assertions in the
same ingest pass. The assertions are a labelled aid: delivery does not flow
through them (DATA_TRUTH Amendment 1 DD2/DD3), and the similarity-proposed
edges keep their own status.

## Why

The D-DT-8 probe measured that no snippet ranking delivers the operator's
material, but the operator's own traceability appendices — the declaration the
operator already wrote about its own documents — parse reliably at document
level. Recording them as labelled, machine_determined assertions puts the
operator's own mapping into the store where the payload builder (DD3) can
surface it as a fact ("your document maps this Part to §3.2") without ever
mistaking a declaration for read-verified evidence — the exact confusion that
made the similarity edges unusable as a delivery path.
