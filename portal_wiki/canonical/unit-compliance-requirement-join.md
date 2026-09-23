---
id: unit-compliance-requirement-join
kind: mixed
title: "Compliance requirement→section join — the key the graph and the corpus never shared"
sources:
- type: code
  path: portal/modules/compliance/core/requirement_anchor.py
- type: code
  path: scripts/capture_register_standards.py
- type: code
  path: scripts/anchor_requirements.py
- type: code
  path: portal/modules/compliance/core/enumeration.py
- type: code
  path: tests/unit/test_compliance_requirement_anchor.py
- type: code
  path: tests/unit/test_compliance_requirement_scoping.py
- type: code
  path: scripts/compliance/capture_technical_basis.py
- type: code
  path: tests/unit/test_compliance_technical_basis.py
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

## The corpus the join needs

The backlog was never 33 unreachable PDFs. The Register records `source_pdfs`
with a sha256 for **14 standards** — proof those URLs resolved and those bytes
were fetched. Thirteen of the fourteen had reached the store only as `pymupdf`
sections with `char_start = -1`: structure with no coordinate space, so nothing
could be projected from them and nothing could be anchored into them.
`scripts/capture_register_standards.py` gives each one the `docling`
whole-document capture the reading path actually needs, sha-verifying against
the Register's recorded digest first — a mismatch STOPs that document, because
the Register's structure came from those exact bytes and anchoring against
different bytes produces a join that is silently wrong rather than loudly
absent. `scripts/anchor_requirements.py` then anchors every standard that has
both Register nodes and a capture, and writes the per-standard, per-relation
census.

What is still missing is a different and smaller problem: NERC's per-version
URLs for *older* revisions. The Register holds one revision per standard except
CIP-003, so `valid_at` queries into the past are answerable only where a prior
revision was captured.

## Retrieval and closure scope by identity

`compliance_search(requirement=…)` narrows **before** ranking. The resolution is
two-step and deliberately not a predicate column: a section bears several
relations to a requirement and can bear on several requirements, so a
multi-value column would need `LIKE` matching on ids — and `'CIP-007-6 R2'` is a
substring of `'CIP-007-6 R2 Part 2.2'`, so `LIKE` is wrong here, not merely
inelegant. Repeated index rows are also out, because they break
`chunk_id = section_id`. So the requirement resolves to exact section ids in
SQLite and those ids are pushed as `chunk_id IN (…)` through `predicates.build`,
composed with the clock clauses by `AND`. Above a measured ceiling the tool
returns `honest-BLOCKED` naming the count rather than falling back to an
unfiltered search, which would look filtered.

`enumeration.population_for_requirement` is the closure-side twin: the
requirement's population comes from the join, and the structural walk survives
as a **named** fallback — `population_method: "proximity"`, never a silent
substitution, because an absence claim resting on a guess must be visibly weaker
than one resting on the join.

## Measures and the Technical Basis, without the verdict engine

`regulatory_bundle` owns the whole semantic content of a revision — the Measures
column and the `M<n>` statements, the Guidelines and Technical Basis per
requirement and per Part, the rationale boxes — and all of it was reachable only
through `resolve_governing_bundle`, which re-parses the PDF at call time.

The GTB text is **already captured**: it sits in `full_text` as prose under its
own heading path. So `requirement_anchor.anchor_bundle_spans` adds nothing to
`source_sections` — it locates each span in the captured character space and
writes a `requirement_sections` row with `relation='technical_basis'` pointing at
the sections that already contain it. Zero new sections, one new table's rows,
and the material becomes readable, findable, scopeable and countable
independently of the verdict engine. `regulatory_bundle.py`, `cip_extract.py`
and `cip_register.py` stay: they are the regulatory extractor.

A Measures lead-in is scoped to its `M<n>` statement rather than the whole
extracted region, because `regulatory_bundle` bounds a lead-in at the start of
the next region and the span therefore runs through the entire requirements
table. Attaching all of it to every Part would join Part 2.1's Measures cell to
Part 2.4 — a citation that looks correct and cannot be checked afterwards.

## The capture is never edited

The module writes nothing to `source_sections`. `assert_faithful` raises on
overlapping spans, and a `table_row` already holds the requirement text, the
applicable-systems column and the Measures column as one unit, so every
relationship lives in the join and the capture is never edited.

## Technical basis from a separate Technical Rationale

A standard has two layers, and procedure reviews need both. The normative text
says what is required. The Guidelines and Technical Basis (GTB) say what the
requirement is for and how an entity is meant to meet it. Older versions
carry GTB inside the standard, and `anchor_bundle_spans` locates it by exact
text. Newer versions moved it into a separate Technical Rationale document,
where the exact-text route has nothing to locate.
`anchor_rationale_document` places each TR section on the requirements its
OWN heading names ("Rationale for Requirement R4", "Requirements R1 and R2",
"Attachment 1 Section 6 Part 6.3"). It records `anchor_method='heading'`, so
this placement is never read as a verbatim anchor. A section whose heading
names neither a requirement nor an attachment section is left unplaced and
reported. A bare "Section 4" is the standard's applicability section, so it
is never guessed onto a Part.

Once a TR is placed per requirement, `reading_assembly` stops carrying it
whole in the fixed body. Whole, it repeated every requirement's rationale in
every reading and put CIP-004-7 and CIP-010-4 material near 100k characters,
against a 32k-token seat.

Measured 2026-09-22: eight register versions' TR PDFs (CIP-003-9, 004-7,
005-7, 008-6, 010-4, 011-3, 012-2, 013-2) were acquired and registered but
never captured. The sync registers without capturing, and the materializer
walked only the last manifest. `materialize_regulatory_corpus.capture_registered`
now captures any registered-but-uncaptured regulatory revision, hash-match or
skip, on every materialize. `scripts/compliance/capture_technical_basis.py`
runs capture and placement and receipts the coverage before and after.

