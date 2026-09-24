---
prompt_version: mapping-v2-2026-09-24
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

## Relation boundaries — where wrong relations come from

Adjudication measured where wrong relations enter; these four boundaries are
that measurement, written as rules. Decide the relation from what the cited
sentence itself does, never from the topic it shares with the requirement.

1. **A row that NAMES the requirement is a REFERENCE, never IMPLEMENTS.** A
   traceability row, mapping cell, or index line that quotes a requirement's
   words or cites its number ("Requirement R2 Part 2.2 (CIP-006 R2.2)") is the
   operator POINTING at the requirement — the pointing is the reference; the
   quoted words are the standard's, not the operator's performance of them.
   IMPLEMENTS requires the section's OWN words to carry the duty.
2. **A scope or purpose statement implements nothing.** "The scope of this
   procedure includes …", "This plan is applicable to …", "The purpose of this
   process is …" bound a document; they are not a step that performs a Part's
   duty. Unless the Part's duty IS to define that scope, the sentence supports
   no relation.
3. **The sentence must carry THIS requirement's demand, not a neighbour's.**
   Check the sentence against the requirement's own text in the material: a
   sentence that states a different Part's duty (the provision one Part over,
   the check one Part below, the notification where retention is demanded) or
   another standard's duty shares only vocabulary — that is not an edge to
   this requirement at all. An appendix mapping row that stops at section
   level ("mapped to Section 3.7") without reaching this Part names no edge
   here either.
4. **A table of contents references nothing in particular.** TOC lines and
   boilerplate introductions to a cross-reference table support no relation.

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
