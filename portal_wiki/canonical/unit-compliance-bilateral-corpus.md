---
id: unit-compliance-bilateral-corpus
kind: mixed
title: "Compliance bilateral corpus — faithful whole-document capture"
sources:
- type: code
  path: portal/modules/compliance/core/capture.py
- type: code
  path: portal/modules/compliance/core/glossary.py
- type: code
  path: portal/modules/compliance/core/section_index.py
- type: code
  path: portal/modules/compliance/core/reading_assembly.py
- type: code
  path: portal/modules/compliance/core/notes.py
- type: code
  path: portal/modules/compliance/core/reader.py
- type: code
  path: portal/modules/compliance/core/candidate_links.py
- type: code
  path: scripts/project_compliance_sections.py
- type: code
  path: scripts/materialize_regulatory_corpus.py
- type: code
  path: tests/unit/test_compliance_capture.py
- type: code
  path: tests/unit/test_compliance_glossary.py
- type: code
  path: tests/unit/test_compliance_regulatory_corpus.py
- type: code
  path: tests/unit/test_compliance_section_index.py
- type: code
  path: tests/unit/test_compliance_reading_assembly.py
claims:
- probe: compliance.capture.unit_kinds
  contains: table_row
- probe: compliance.capture.unit_kinds
  contains: figure_caption
- probe: compliance.store.tables
  contains: document_texts
- probe: compliance.store.tables
  contains: source_table_cells
confidence: high
tags:
- compliance
- retrieval
- authored-v1
---

`portal.modules.compliance.core.capture` is the regulatory and internal ingest
path for TASK_COMPLIANCE_BILATERAL_CORPUS_AND_CONVERSATION_V1. It exists because
every previous compliance extractor **selected**: `cip_extract._requirement_block`
bounded its search to a standard's "Requirements and Measures" section and
terminated at `Violation Severity Level`, so a CIP standard's VSL tables, version
history, Section 4 applicability, Section 6 background and evidence-retention
section were never captured at all. An analyst cannot ask what a requirement is
*for* when the text stating its intent was discarded at ingest.

## Why

An analyst asks what a requirement is *for*, whether what we do achieves it, and
where we fall short. Those questions are answered from the parts of a standard
that explain its intent — the Guidelines and Technical Basis, the Rationale, the
Background section's reading conventions — and from the parts that show what an
auditor will look for, the VSL tables and the evidence-retention section. Every
one of those was discarded at ingest. Capture is not a performance concern or a
tidiness concern: it is the difference between a corpus that can answer the
question and one that cannot, and it is the only place a discard can still be
prevented rather than worked around.

It also makes absence provable. A boundary receipt asserting "we read the
declared population and nothing addresses this" is worth exactly as much as the
population it names. A population assembled by a selecting extractor cannot
support the claim; a total tiling can.

## What a capture is

`capture_document(path)` runs the layout-aware reader already in the retrieval
stack (`portal.platform.retrieval.extraction.read_document` → docling) and lays
the whole document out as an ordered tiling of `CapturedUnit`s over one
character coordinate space, `CapturedDocument.full_text`.

A unit records **where it is**, never what it means:

| field | source |
| --- | --- |
| `ordinal` | reading order, 0-based |
| `heading_path` | the document's own outline, via a heading-level stack |
| `page_start` / `page_end` | the reader's provenance |
| `char_start` / `char_end` | half-open span in `full_text` |
| `unit_kind` | `prose`, `table`, `table_row`, `list_item`, `figure_caption` |

There is no requirement parser, no VSL parser, no rationale parser and no
keyword classifier in this module, and there must never be one. `role` survives
on the stored section, populated by `positional_role()` from the top-level
heading — it is a positional label, and **no code path may use it to bar a
passage from retrieval, return or citation**.

## The three fidelity properties

`fidelity_report()` measures them and `assert_faithful()` refuses a store write
that fails any, so a lossy capture cannot reach the canonical store:

1. **total character coverage** — the units tile `full_text` with no gap and no
   overlap; every character belongs to exactly one unit. The tiling separator
   belongs to the unit it follows, which is what makes the partition gapless.
2. **total page coverage** — every page `1..N` carries at least one unit. A page
   the layout reader returns nothing for is captured verbatim from the page's
   own text; silence about a page is the one thing a fidelity capture may not do.
3. **empty reconstruction diff** — concatenating the units in ordinal order
   reproduces `full_text` byte for byte.

A tiling is trivially 100% of itself, which proves nothing, so a fourth check
runs against the **reader** rather than the capture: `reader_strings` holds every
distinct normalised string docling produced — each item's text and each table
cell's text — and `reader_strings_absent` must be zero. That check is what caught
a real defect during P1: table caption rows flagged as column headers were being
dropped while self-coverage still read 100%.

## Tables stay tables

Flattening a CIP requirements table loses which Measure belongs to which Part and
which Applicable Systems row governs which requirement. A `TableItem` becomes one
`table` unit carrying the caption and every header row, plus one `table_row` unit
per body row with its `cells` and the `columns` they sit under. Both carry the
reader's `table_ref`, so a row resolves to its parent table. Measured on
`cip-007-6.pdf`: the R2 table arrives as four separate one-row tables (docling
splits it per page), yielding Part rows `2.1`, `2.2`, `2.3`, `2.4`, each with its
own four cells under `Part | Applicable Systems | Requirements | Measures`.

## Where it lands

Migration 11 adds the positional columns (`unit_kind`, `ordinal`, `char_start`,
`char_end`, `heading_path`) to `source_sections`, the `document_texts` table that
holds a revision's captured coordinate space, and `source_table_cells` for
structured rows. `store_capture()` writes a capture as a same-fingerprint
rebuild: sections written by this extractor for the revision are replaced
wholesale, and sections written by another extractor are untouched.

The internal corpus is captured on the same terms. `internal_corpus.sectionize`
gained `_complete_tiling`, which clips overlaps and fills gaps so a document's
sections partition its text exactly, and enforces one invariant in one place —
**a section's text is its span**. Measured on the 68-document operator corpus
before that pass: 63 documents lost material at a section boundary (the
characters between a table-of-contents page and the next heading, and the tail
after the last heading). After it: zero.

## The Glossary is a corpus, not a footnote

`portal.modules.compliance.core.glossary` acquires the *Glossary of Terms Used in
NERC Reliability Standards* from https://www.nerc.com/glossary-of-terms, whose
`window._model` payload carries one structured record per term — verbatim
definition, acronym, status, docket, Board-adoption date, effective date,
inactive date. Records are located **by shape**, not by JSON path, so a CMS
reshuffle fails loudly instead of yielding zero terms.

Each term becomes a section in the same tables as everything else, so a Glossary
entry is the same kind of addressable thing as a requirement Part or an operator
procedure section. `nerc_source_sync` acquires it beside the standards with the
same byte-hash UNCHANGED semantics.

Resolution honours both clocks and never guesses:

* the Glossary carries a term's **future successor beside its enforceable
  revision** (measured live: 330 terms, with `Protected Cyber Assets` enforceable
  to 2028-06-30 and `Protected Cyber Asset` effective from 2028-07-01), so
  `resolve_terms` selects by `valid_at` — defaulting to today — and names the
  other revisions rather than hiding them;
* an acronym resolves only when every entry carrying it belongs to one term;
* a trailing plural `s` is normalised, because NERC renames headwords between
  revisions and a requirement written in the singular must still reach its own
  definition. Verified against the live Glossary: exactly one bucket collapses
  two spellings and their windows are sequential, so no two concepts merge;
* a term the Glossary does not carry comes back explicitly unresolved, naming
  itself. Never guessed, never silently empty.

`assessment_source.resolve_governing_bundle` now resolves the
`external_glossary` disposition instead of only recording it: a bundle whose
standard has no definitions section carries the Glossary terms its own duty text
depends on, each with its section id, revision and effectivity.

## Symmetric materialization

`scripts/materialize_regulatory_corpus.py` is the twin of
`materialize_internal_corpus.py`. Every acquired official artifact becomes a
`source_documents` row with `jurisdiction='US'` and its own `source_kind`, a
`document_revisions` row keyed on byte hash carrying lifecycle dates **parsed
from the One-Stop-Shop workbook and never from a filename**, and a faithful
capture as `source_sections` / `source_spans`. After it runs, the two sides are
the same kind of thing in the same tables and the only difference between them
is the `jurisdiction` column.

Three properties it owns:

* **hash-match or fail.** Every artifact is re-hashed against the acquisition
  manifest. A mismatch, or a manifest naming a file that no longer exists, is a
  hard failure — a document whose bytes moved is not the document the lifecycle
  facts describe.
* **one identity per standard.** `canonical_identity` derives
  `NERC/CIP-007-6` from an artifact's role and the standard id in its name, so
  two acquisitions of one standard are two revisions of one document. The
  version's own case is preserved: the register spells it `CIP-002-5.1a`.
* **one jurisdiction, one spelling.** The store carried both `US` and
  `United States` for the same jurisdiction, so every jurisdiction-filtered
  query was wrong by construction. Normalised to `US`.

`temporal_selection.select_document_effectivity` answers the two-clock question
from the regulatory corpus — `document_revisions.effective_date` /
`inactive_date`, both from the workbook — where `select_revision_effectivity`
answers it from the pinned register. Verified live on CIP-007: both paths select
`6` today with `7.1` future, and both select `7.1` at 2029-01-01 with `6`
historical. An undated revision is never read as always-in-force, and a revision
recorded after the requested `known_at` answers `UNKNOWN_KNOWLEDGE`.

## One identity space

`core/section_index` emits the retrieval index FROM `source_sections`, at
section granularity, with `chunk_id = section_id`. Before it, 68 internal
documents existed as 2,508 classified sections with `isection-…` ids and as
2,636 docling chunks with sha1 ids, and the intersection of those two id sets
was **empty** — a hit could not be resolved to a section, and
`_boundary_proof_id`'s `set(examined_sections) == {chunk_id}` check could never
pass. Measured after the change: 50 of 50 live search hits resolve to a
canonical section.

Three populations are kept apart because they mean different things. A
revision's capture is a *total* cover of that revision, so for a captured
revision the captured sections ARE the eligible population; pre-capture sections
on the same revision are **superseded**, not missing; revisions with no capture
are **uncaptured documents**, named, and the corpus is not whole while any
remain. Splitting a long section into `<section_id>#<n>` sub-units is a
projection detail — `parent_section_id` resolves them back.

**The boundary is a fact, not a fixture.** `boundary_receipt` emits
`eligible_sections`, `examined_sections` and `document_revision_hashes` from the
store, and `assessment_source.acquire_exhaustively` reads the whole declared
population rather than a top-k window. Demonstrated live on CIP-007-6's 278
sections: a complete scoped acquisition yields
`boundary-91b01811468966b66db1`, and withholding one section yields `""`.

Freshness is tracked **per corpus**: one store-wide hash would mark the
regulatory index stale the moment somebody writes an operator note, which is
false and teaches people to ignore the signal. `--restamp` re-records a
manifest only for corpora whose index matches the store row for row.

## The reading assembly

`core/reading_assembly.assemble` replaces the top-k keyhole. For a requirement
it gathers, by document structure and recorded graph edges rather than by
relevance score: the requirement and its Parts with their own cells, the
Measures, the Guidelines and Technical Basis, the Rationale, the VSL rows,
Section 4 applicability, Section 6 background and its reading conventions, the
resolved Glossary terms, the implementation plan and technical rationale, the
version history, the linked operator sections in full, and the operator's own
notes. Measured on CIP-007-6 R2: **15,240 tokens, nothing omitted** at the
default 60k budget. Anything the budget cannot hold is named in `omitted`.

Selecting the sections under `Guidelines and Technical Basis > Requirement R2:`
reads the document's own outline; it decides nothing about what any passage
means. Nothing is marked ineligible to cite.

An operator note (`core/notes`) is a source like any other — a document, an
immutable revision, a section — so it is citeable, resolvable and projectable by
exactly the same machinery, and it outranks a stored answer.
