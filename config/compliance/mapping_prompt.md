---
prompt_version: mapping-v1-2026-09-18
rationale: >
  The map unit of the sweep (PROVE_THEN_SCALE_V1 P2/P4). The reading prompt
  (reading-v2.1) serves a conversation; this one serves a determination: the
  model is handed a requirement's whole population and asked to state the
  mapping the reading itself supports — typed, with the sentence that
  justifies each edge, and with new pairings named explicitly so the
  graph's next reading can start from them. No tools, no loop: the material
  is complete by construction, because requirement_scope.population states
  the scope and the renderer handed all of it over.
---

You are determining the mapping between one NERC CIP requirement and the
operator's own documents.

Above is the complete material: the standard's fixed body, then this
requirement's own scope — every section the standard's own join anchors to it
and every operator section linked to it by a recorded edge, each entry
labelled with its side and its standing. An operator edge marked `proposed` is
a recorded link that no human has approved; treat the label as the edge's
standing, and never describe a proposed edge as approved.

## What you are deciding

For each OPERATOR section in this requirement's scope, which relation does it
bear to the requirement?

* **IMPLEMENTS** — the section performs the duty, or commits the operator to
  performing it: a procedure step that carries out what the Part requires, a
  policy clause that binds the operator to it.
* **EVIDENCES** — the section records, demonstrates, or provides the evidence
  of the duty: logs, workbooks, records, retention statements.
* **REFERENCES** — the section points at the requirement — a traceability
  appendix, a cross-reference table — without itself performing or evidencing
  it.

Decide from the section's own words. Quote the exact sentence that justifies
each determination, verbatim, from the section's text. If a section's text
does not support a relation, say so — an honest "the text does not support a
relation" is worth more than a guessed edge.

## The two things you must never do

1. **Never determine an edge you were given.** Every operator section below
   already carries a recorded link to this requirement — its standing line
   says so. Where the text supports that link, you are CORROBORATING it: say
   so in prose, with the sentence. A determination block entry for a pairing
   the store already holds is wasted work.
2. **Never invent a pairing without naming the requirement.** Where a section
   you are reading bears on a DIFFERENT requirement — the overlap the standards
   actually have; a patch section that also serves CIP-010-4, a traceability
   row that maps many Parts — you may determine that pairing, naming the other
   requirement explicitly in its `requirement_id` field.

## The determinations block

End your answer with one fenced block:

```json
{"determinations": [
  {"requirement_id": "CIP-007-6 R2 Part 2.3",
   "section_id": "isection-...",
   "relation_type": "IMPLEMENTS",
   "sentence": "the exact sentence from the section's text",
   "confidence": "high"},
  ...
]}
```

`confidence` is `high`, `medium`, or `low` — how directly the sentence states
the relation. Only NEW pairings go in the block: pairings this material does
not already record. Every entry's `sentence` must appear in the named
section's text; the system checks, and an edge whose citation does not
resolve verbatim is not written.
