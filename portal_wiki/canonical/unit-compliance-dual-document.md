---
id: unit-compliance-dual-document
kind: what
title: "Compliance dual-document payload — a question returns the standard AND the operator's documents"
sources:
- type: code
  path: portal/modules/compliance/core/dual_document.py
claims: []
confidence: high
tags:
- compliance
- delivery
- payload
created_at: 1760000000.0
updated_at: 1760000000.0
---

# Compliance dual-document payload

A question is a dual-document request: it should return the standard's
normative text AND the operator's own documents for that standard, whole, so
the model can converse about both and state the facts they contain.
`dual_document.build` is the one delivery path both reader-facing tools use:
`compliance_context(mode=material, ref)` resolves by address (a named
requirement expands to every Part; similarity never resolved Part sets), and
`compliance_search(query)` with no requirement resolves the top-2 distinct
standards through the governing-anchor lane before attaching the payload
beside its ranked list (which stays, never replaced).

The payload, in order: the standard's normative Parts from the governing
anchors (no fixed body — `compliance_read` serves it on request); the
operator's document set — the filing folder ∪ documents whose own
traceability appendix names the standard — whole, in document order, with
structure roles stripped and every section labelled
`[document § heading] (section_id)`, because long-context attribution failed
on every serving route until the document name rode on each section; the
operator's notes; and the operator's traceability facts as labelled
declarations.

The payload is priced before it is returned, at the measured minimum
bytes-per-token, against the declared window minus the predict budget minus a
recorded persona/tools reserve. A document that does not fit whole is
deferred and listed by title with a `compliance_read` instruction — sections
are never clipped and the engine is never allowed to truncate.

## Why

A month of reader arms could not move correctness because the fact-bearing
material never reached the model: snippet ranking topped out at 14/27 and the
edge-selected material at 11/27, while the document SET holds 24/27 and the
128k seat holds a 124.7k-token real-document read without truncation. The
data truth was that the unit of delivery is the document, not the snippet —
so the tools now return documents.
