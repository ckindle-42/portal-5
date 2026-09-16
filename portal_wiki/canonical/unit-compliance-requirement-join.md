---
id: unit-compliance-requirement-join
kind: mixed
title: "Compliance requirement→section join — the key the graph and the corpus never shared"
sources:
- type: code
  path: portal/modules/compliance/core/requirement_anchor.py
- type: code
  path: tests/unit/test_compliance_requirement_anchor.py
claims:
- probe: compliance.register
  contains: CIP-007-6
- probe: compliance.store.tables
  contains: requirement_sections
- probe: compliance.store.tables
  contains: requirement_anchor_misses
confidence: high
tags:
- compliance
- retrieval
- authored-v1
---

## Why

Two halves of the same ask were built and never joined.

`portal/modules/compliance/data/nerc_cip_register.json` is the **structure**:
255 requirement nodes across 14 standards, every node carrying its exact
`verbatim_text` plus `vrf`, `time_horizon`, `lifecycle_state`, `valid_from` /
`valid_to`, `authority_tier`, `source_pdf` and `source_pages`. The node id is
literally `CIP-007-6 R2 Part 2.2`.

`source_sections` is the **fidelity**: a total-cover tiling of a captured
revision's character space, asserted by `capture.fidelity_report` and enforced
by `capture.assert_faithful`. It records where a unit *is*, never what it
means.

`RegisterNode` has no `section_id`. `source_sections` has no requirement
reference of any kind. The only overlap is `source_pdf` + `source_pages`, which
is page granularity — a page holds many sections and a Part can span pages. So
there was no way to retrieve *the sections constituting R2 Part 2.2*, and two
long-standing oddities follow directly from that one absence:
`reading_assembly` gathered by heading-path proximity because proximity was the
only option available, and `resolve_governing_bundle` re-parsed the PDF at call
time to obtain text for an identity it already held.

## The anchor is exact, and that is the point

`portal.modules.compliance.core.requirement_anchor` supplies the key, and the
method is **exact, never fuzzy**. `document_texts.full_text` is the captured
revision's character space with a byte-exact reconstruction guarantee, and every
section carries `char_start` / `char_end` in it. Locate a node's `verbatim_text`
in that space by exact substring match after one normalisation — NFKC, the
licensed `_SUBSTITUTIONS`, whitespace collapse, nothing else — and the sections
whose half-open span overlaps the located range *are* that requirement's
sections. A fuzzy match would produce citations that look correct, cannot be
checked afterwards, and would be built on; so a text that does not occur is
recorded as `UNANCHORED` with a named reason instead.

## Two renderings of the same bytes

Two renderings of the same bytes have to be reconciled to make that work. The
Register's text comes from pymupdf reading the PDF as flowing prose; the
capture's `full_text` is the byte-exact concatenation of docling units, where a
`table_row` unit's text is `" | ".join(cells)`. `_SUBSTITUTIONS` is the closed
list of rendering artefacts admitted between the two readers, and an addition to
it is **mechanical, not a judgment**: re-run the anchor with and without the
candidate and require zero change to any already-anchored range plus at least
one `UNANCHORED` converted. `U+F0B7` — the Symbol-font list bullet in the
Private Use Area, which docling keeps and pymupdf renders as `-` — was admitted
on that test (zero ranges changed, 9 conversions).

## Relations narrow, they never bar

A requirement's material is relation-typed: `governing` is the duty text itself,
`measure` the evidence column, `applicable_systems` the systems column,
`technical_basis` the Guidelines and Technical Basis. In a CIP requirements
table all three of the first often land on the *same* `table_row` section,
because a row is one unit — which is why `relation` is a column on the join
rather than a reason to cut new sections. A relation narrows *which* of a
requirement's material is being asked for; per `capture.positional_role`'s rule
it must never bar a passage from a general search.

## The two primitives

`Repository.sections_for_requirement(requirement_id, relations=…, valid_at=…)`
is the retrieval primitive that did not exist: section rows in reading order,
the revision selected by `document_revisions`' own clock. It defaults to
`("governing",)` so a caller that wants only the duty text gets only the duty
text. `Repository.requirements_for_section(section_id)` is its exact inverse —
a reader looking at a passage can say which requirements it bears on and how,
which makes a citation checkable in both directions rather than only forwards.
`Repository.record_anchors` is the idempotent upsert into
`requirement_sections`, with every miss landing in
`requirement_anchor_misses` so an unanchored requirement is a queryable fact
rather than a line in a report nobody re-reads.

`section_index.resolve_sections` rides the Register's facts in on a `governing`
join: `requirement_id`, `vrf`, `time_horizon`, `applicable_systems` and
`lifecycle_state` are READ from the register node. Where the Register's
`authority_tier` and the document-derived projection disagree, the
disagreement is reported on the entry and **neither value is overwritten** —
two derivations of one fact silently differing is precisely the failure this
module has already had twice.

## The capture is never edited

The module writes nothing to `source_sections`. `assert_faithful` raises on
overlapping spans, and a `table_row` already holds the requirement text, the
applicable-systems column and the Measures column as one unit, so every
relationship lives in the join and the capture is never edited.
