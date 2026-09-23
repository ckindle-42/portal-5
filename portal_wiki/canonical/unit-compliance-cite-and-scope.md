---
id: unit-compliance-cite-and-scope
kind: mixed
title: "Compliance cite-and-scope — quotes as citations, documents carrying their scope"
sources:
- type: code
  path: portal/modules/compliance/core/citation_by_quote.py
- type: code
  path: portal/modules/compliance/core/document_scope.py
- type: code
  path: scripts/compliance/derive_document_scope.py
- type: code
  path: scripts/compliance/scope_effect.py
- type: code
  path: scripts/compliance/sweep_edge_set.py
- type: code
  path: scripts/compliance/cite_and_scope_measure.py
- type: code
  path: tests/unit/test_compliance_citation_by_quote.py
claims:
- probe: compliance.cite_and_scope
  contains: quote-min-part-chars=4
- probe: compliance.cite_and_scope
  contains: scope-read-budget-chars=9000
- probe: compliance.cite_and_scope
  contains: family-normal-form=CIP-NNN
confidence: high
tags:
- compliance
- citation
- authored-v1
---

`portal.modules.compliance.core.citation_by_quote` is the verbatim check
inverted over the whole store (CITE_AND_SCOPE_V1 §P1): the citation an answer
carries is a double-quoted span of a section's exact words, and
`resolve_quote` finds every section whose document contains it — typography
folded (all quote glyphs to one character, dash-space from PDF line wraps,
trailing absorbed punctuation), elision marks splitting a span into parts
that must ALL appear verbatim in ONE document. A paraphrase finds nothing and
that finding is the answer; a quote matching several sections is reported
with every match. The ground truth is the 451 stored determination
provenance sentences, which the resolver reproduces at recall 1.0
(reports/compliance/cite_and_scope/p1/quote_resolution.json).

`portal.modules.compliance.core.document_scope` is the store side of what
each operator document STATES it serves (§P2): one bounded seat read per
document against its own opening and scope material, every standard claim
carrying quoted evidence validated by folded containment before storage
(migration 20, `document_scope`). Only evidence-backed families are ever
stated. The signal reaches the reader as **visible provenance**:
`reading_material.render` puts a `> document scope:` line beside every
operator section, saying what its document serves and whether that includes
the reading's own standard. It excludes nothing, and a document with no scope
row gets no line. `build_links`' filter and prior modes remain, measured and
not adopted: family-wide, a hard filter removed about a quarter of all
adjudicated-SUPPORTED pairs, and the prior displaced nothing on a
threshold-gated population (reports/compliance/cite_and_scope/p2/scope_decision.json).
The problem both modes were aimed at is similarity-only scoping, which paired
the operator's physical-security material to CIP-002 asset-categorization
requirements because they share vocabulary: CIP-002 adjudicated 0.31 while
the family ran 0.81.

**Measuring a re-sweep.** The store only accumulates reading-derived edges.
A re-read either corroborates an edge or leaves it alone, and never retracts
one, so a store-wide precision mixes every campaign's readings.
`sweep_edge_set.py` rebuilds the edges one sweep affirmed from its stored
`reading_runs`, and splits the baseline edges into reaffirmed, no longer
affirmed, and requirement-not-re-read. `adjudicate_determinations.py
--assertions/--carry` judges only that set, and carries a prior verdict when
the claim is unchanged. `cite_and_scope_measure.py` compares like with like:
the new sweep's set against the previous sweep's
(p3/baseline_edge_set.json). The conversational grounding check resolves a
`cite_as` token by the rule that minted it (`addressing.resolve_cite_as`: the
letter is the side, not the id prefix), and material served into a
conversation asks for quotes, not render handles.

The driving scripts are idempotent: `derive_document_scope.py` skips
documents already scoped, and `scope_effect.py` measures each mechanism
against the baseline adjudication before any family-wide commitment.

## Why

Because three structural fixes moved a 20-hex identifier around the model's
prompt and the transcription failures kept coming — dropped characters, added
characters, two ids concatenated, three distinct failure modes in six answers,
each one voiding a substantive claim. And because a requirement's population
scoped by similarity alone cannot tell *mentions this asset class* from
*implements this requirement*: CIP-002's content IS the shared vocabulary, and
it adjudicated 0.31 against a family at 0.81. Both fixes move the judgment to
something that can be checked by reading: a quote is verified against the
words themselves, and a scope claim against the document's own stated scope.
