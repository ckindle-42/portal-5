# BILATERAL_CORPUS_V1 — TASK_COMPLIANCE_BILATERAL_CORPUS_AND_CONVERSATION_V1

Baseline `main` @ `02b347dc`. Every figure below is from a live query or a live
run on this machine, never from a document.

---

## §1 — P0 bilateral census, cost, and §0 dispositions

### 1.1 Baseline

| item | value |
| --- | --- |
| HEAD | `02b347dc` |
| `uv run pytest tests/unit/ -q` | **1991 passed, 4 skipped**, 198s |
| `python3 scripts/validate_system.py` | **210 pass · 0 fail · 3 warn · 0 skip**, 312s |
| last check letter in use | `GQ` (next free: `GR`) |
| store schema version | 10 |

### 1.2 Knowledge bases in the compliance composition

`store.list_kbs(prefix="compliance_")` — 32 KBs, of which one is the product
corpus and the rest are eval/acceptance artefacts:

| kb_id | rows | stage stamp |
| --- | --- | --- |
| `operator_corpus` | 2,636 text chunks, 68 distinct `source_file` | docling, contextualize, fts, visual_scope=figures |
| `review_queue`, `substrate_eval`, `substrate_eval2`, `y25_baseline`, `y25_docling`, `acceptance`, `acceptance-c02`…`acceptance-c26` | eval-only | — |

**There is no `nerc_corpus`.** The regulatory side is not in any index.

Active projection manifests (`index_manifests`):

```
proj-20260915T174512Z-retrieval  retrieval  active  files_ingested 68  chunks_added 2636
proj-20260915T174512Z-graph      graph      active  nodes 292  edges 255
canonical_fingerprint 2b9b6e44…76881 (both)
```

### 1.3 `source_documents` by jurisdiction and kind

| jurisdiction | source_kind | documents |
| --- | --- | --- |
| `US` | `official_standard_material` | 6 |
| `United States` | `regulatory_standard` | 15 |
| `internal` | `procedure` | 28 |
| `internal` | `work_instruction` | 26 |
| `internal` | `evidence_specification` | 5 |
| `internal` | `plan` | 5 |
| `internal` | `process` | 2 |
| `internal` | `policy` | 1 |
| `internal` | `unknown` | 1 |

Two jurisdiction spellings exist for one jurisdiction (`US` from
`nerc_source_sync._register_in_store`, `United States` from
`materialize_regulatory_bundles`). Recorded as a defect to reconcile in P3.

### 1.4 `source_sections` by jurisdiction and role

| jurisdiction | role | sections |
| --- | --- | --- |
| internal | OPERATIVE_PROCEDURE | 1,229 |
| internal | WORK_INSTRUCTION | 783 |
| internal | DOCUMENT_CONTROL | 230 |
| internal | COMMENTARY | 72 |
| internal | TABLE_OF_CONTENTS | 65 |
| internal | DEFINITION | 63 |
| internal | INTERNAL_POLICY | 60 |
| internal | EVIDENCE_SPECIFICATION | 40 |
| internal | TRACEABILITY_ASSERTION | 33 |
| internal | (empty) | 1 |
| **internal total** | | **2,576** |
| United States | (empty) | 254 |
| United States | MEASURE | 25 |
| United States | TECHNICAL_BASIS | 24 |
| United States | REGULATORY_REQUIREMENT | 7 |
| US | REGULATORY_REQUIREMENT | 26 |
| US | MEASURE | 26 |
| **regulatory total** | | **362** |
| **store total** | | **2,938** |

### 1.5 CIP-007-6 — what exists as sections, and what does not

Revision `5b7820e7…a8bd` (`data/cip_pdfs/cip-007-6.pdf`, 51 pages, 84,471 chars
of extracted text) carries **74 sections**:

| component | present? | evidence |
| --- | --- | --- |
| Requirements (R1–R5 lead-ins) | **yes** | 5 `… lead-in` sections, role `REGULATORY_REQUIREMENT` |
| Requirement Parts (1.1 … 5.7) | **yes** | 20 `CIP-007-6 R<n> Part <p>` sections |
| Measures | **yes** | 20 `… Measures` + 5 `M<n> Measures lead-in`, role `MEASURE` |
| Guidelines and Technical Basis | **yes** | 19 sections, role `TECHNICAL_BASIS`, pages 40–48 |
| Rationale | **yes, only inside GTB** | 5 `Guidelines and Technical Basis Rationale R<n>` sections, pages 49–50 |
| **VSL tables** | **no** | zero sections; terminator `\bViolation Severity Level` in `cip_extract._requirement_block` |
| **version history** | **no** | zero sections |
| **Section 4 applicability / exemptions** | **no** | zero sections |
| **Section 6 background / reading conventions** | **no** | zero sections |
| **Section C compliance + evidence retention** | **no** | zero sections; terminator `^[ \tC]*\.?\s*Compliance\s*$` |
| **NERC Glossary** | **no** | no `source_documents` row of any glossary kind; `acquisition_manifest.json` has no glossary artifact |

Coverage: the 74 sections' spans total well under 20% of the document's 84,471
characters, and **`source_spans.char_start` is 0 for every regulatory section**
— the spans are offsets into the section's own extracted string, not into the
document. There is no document coordinate space on the regulatory side.

Pages are also absent on the Part sections themselves (`page_start` NULL for
all 20), present only on Measures and GTB.

### 1.6 Glossary term resolution

No Glossary term resolves. `regulatory_bundle` sets
`definitions_disposition = "external_glossary"` (line 297) for a Part that
defers to the Glossary and nothing fetches it — the disposition is the code
correctly noting a deferral that is never honoured.

### 1.7 `relationship_assertions`

| status | derivation | rows |
| --- | --- | --- |
| proposed | `folder_cartesian` | 1,070 |
| proposed | `folder_placeholder_org` | 272 |
| proposed | `semantic_reading` | 9 |
| revoked | (empty) | 1 |

Zero approved edges. Every mapping in the store is a proposal.

### 1.8 Projection cost — measured, not estimated

Measured live against the VL retrieval server (`:8942`,
`Qwen3-VL-Embedding-2B-mxfp8`, dim 2048, `VL_EMBED_MAX_ITEMS=24`) on
2026-09-15, embedding 200 sections sampled evenly across the store with their
**real** extracted text:

```
sections with spans   2,928
char length           mean 1,045  median 247  p90 1,566  max 77,587
sample                200 sections, 150,410 chars
wall time             132.82 s
per section           0.664 s
```

Extrapolation:

| population | sections | projected |
| --- | --- | --- |
| internal | 2,576 | **28.5 min** |
| regulatory (post-P1 capture, est. 3,000) | ~3,000 | **33.2 min** |
| **both** | ~5,600 | **~62 min** |

**Under the two-hour threshold.** No batching proposal is required; the
projection runs in one pass. The `max 77,587` char section is a single
unbroken internal section and will split into sub-units under P4.1.

### 1.9 §0 claim dispositions

| claim | disposition | evidence |
| --- | --- | --- |
| **0.1** One corpus, not two | **CONFIRMED** | `ingest.py::ingest_folder` docstring reads *"Ingest the operator's folder: policies and procedures together"*; `list_kbs(prefix="compliance_")` has `operator_corpus` and no regulatory KB; the NERC side is reachable only as `resolve_governing_bundle`'s fixed per-Part bundle. |
| **0.2** Regulatory extraction discards what the questions need | **CONFIRMED** | `cip_extract._requirement_block` bounds on `Requirements and Measures` (line 149) and terminates on `^[ \tC]*\.?\s*Compliance\s*$\|\bViolation Severity Level` (line 151). §1.5 shows VSL, version history, Section 4, Section 6 and Section C absent as sections. GTB **is** extracted (19 sections) and **is** marked non-citeable — `reading.py:241` labels it *"not binding text and not selectable as duty evidence"* — and is not in any index. Glossary never acquired (§1.6). |
| **0.3** Retrieval and the graph are parallel extractions | **CONFIRMED, exactly** | 68 documents → 2,636 chunks in `compliance_operator_corpus` with sha1-shaped `chunk_id`s (`0e5f8f11a33c…`); 2,938 `source_sections` with `isection-…` ids. **`len(chunk_ids ∩ section_ids) == 0`.** `_boundary_proof_id`'s `set(examined_sections) == {chunk_id}` check can never pass. |
| **0.4** Absence is unprovable in production | **CONFIRMED** | `grep -rn boundary_receipt` over `portal/ scripts/ tests/`: the only **writers** are `scripts/replay_compliance_reading_family.py:124`, `scripts/verify_compliance_reading_acceptance.py:327`, and three test fixtures. `acquire_candidates` (`assessment_source.py:568`) sets `acquisition_mode`, `completeness`, `candidate_identities`, `n_candidates`, `n_unresolved` — **never `boundary_receipt`** — so `_boundary_proof_id` returns `""` on every production request and every OMISSION is unprovable. |
| **0.5** The interactive surface is a job queue | **CONFIRMED** | `compliance_gaps(operation="start")` default returns a run id to poll (`compliance_mcp.py:840,852`); `_SPAN_EXCERPT_CHARS = 180` truncates every citation span at three call sites (`:569,605,616`). |
| **0.6** Most per-Part machinery cannot change the answer | **CARRIED FORWARD** | Structurally consistent with HEAD — the alignment/council path is wired through `determination.py` and `obligation_alignment.py` with seven seat calls per Part. The byte-identical-verdict measurement is the P10.2 retirement justification and is re-run there rather than duplicated here. |

### 1.10 Additional defects found during the census (not in §0)

* **Two jurisdiction spellings for one jurisdiction** — `US` (6 docs, from
  `nerc_source_sync`) and `United States` (15 docs, from
  `materialize_regulatory_bundles`). Any jurisdiction-filtered query is wrong
  by construction today.
* **`NERC/cip-007-6.pdf` has a `source_documents` row and no
  `document_revisions` row** — the official bytes under
  `data/private/nerc_official/` were never given a revision, while the
  `data/cip_pdfs/` copy was. Two copies of one standard, one registered.
* **`NERC/CIP-007-7.1` (regulatory_standard) has no revision either**; its 52
  sections hang off the `official_standard_material` document instead.

---

## §2 — P1 faithful whole-document capture

New module `portal/modules/compliance/core/capture.py`; migration 11 applied
live (v10 → v11) against the snapshot `data/private/backups/pre-v11-20260916T023321Z.db`.

### 2.1 What was built

`capture_document(path)` runs the layout-aware reader already in the retrieval
stack (`portal.platform.retrieval.extraction.read_document` → docling, the same
path the compliance composition forces its chunker onto) and lays the whole
document out as an ordered tiling of positional units over one character
coordinate space. A unit records `ordinal`, `heading_path` (from the document's
own outline), `page_start`/`page_end`, `char_start`/`char_end` and
`unit_kind ∈ {prose, table, table_row, list_item, figure_caption}`. There is no
requirement parser, no VSL parser, no rationale parser and no keyword
classifier in it.

`role` is kept and populated by `positional_role()` from the top-level heading —
a positional fact. No code path added in this task uses it to bar a passage from
retrieval, return or citation; the P10 verifier asserts that.

### 2.2 Fidelity gates — live, on real PDFs

`uv run python scripts/compliance_capture_fidelity.py <pdfs>`:

| document | pages | sections | chars | coverage | recon diff | unit kinds |
| --- | --- | --- | --- | --- | --- | --- |
| cip-007-6.pdf | 51 | 278 | 80,218 | **100.00%** | **empty** | prose 121, list_item 70, table 31, table_row 55, figure_caption 1 |
| cip-003-9.pdf | 27 | 226 | 44,846 | **100.00%** | **empty** | prose 30, list_item 141, table 14, table_row 41 |
| cip-010-4.pdf | 29 | 186 | 46,346 | **100.00%** | **empty** | prose 31, list_item 104, table 16, table_row 35 |

Zero gaps, zero overlaps, zero missing pages on all three. Capture cost
6–13 s/document.

**The self-coverage number proves nothing on its own** — a tiling is trivially
100% of itself. The gate that matters checks the capture against the *reader*:
`reader_strings` holds every distinct normalised string docling produced (349 for
CIP-007-6, items and table cells alike) and `reader_strings_absent` must be zero.
That check earned itself immediately: the first implementation dropped the
caption row of every requirements table (`CIP-007-6 Table R2 - Security Patch
Management`) because docling flags it as a column-header row, while self-coverage
still read 100.0%. Fixed by keeping every header row on the `table` unit.

### 2.3 What is now captured that was not

Probed live in the CIP-007-6 capture — each of these was absent from the store
before P1 (§1.5):

| passage | units | heading path |
| --- | --- | --- |
| Violation Severity Level | 11 | `2. Table of Compliance Elements` |
| Section 6 Background | 1 | `6. Background:` |
| Evidence Retention | 3 | `1.2. Evidence Retention:` |
| Version History | 1 | `Version History` |
| *"not strictly an 'install every security patch' requirement"* | 1 | `Requirement R2:` |

### 2.4 Tables stay tables

Measured on CIP-007-6: docling splits the R2 requirements table across its four
pages, so the capture yields four one-row tables. Each row carries its own four
cells under `Part | Applicable Systems | Requirements | Measures`:

```
#/tables/2  cols ['Part','Applicable Systems','Requirements','Measures']  rows 1  cells [4]  part ['2.1']
#/tables/3  …  part ['2.2']
#/tables/4  …  part ['2.3']
#/tables/5  …  part ['2.4']
```

Four Part rows, each with its own cells. Cells are persisted in
`source_table_cells` under their column names, so a Measure stays attached to
the Part it belongs to.

### 2.5 The internal corpus, on the same terms (P1.7)

`internal_corpus.sectionize` gained `_complete_tiling`, which clips overlaps,
fills gaps, and enforces one invariant in one place: **a section's text is its
span**. Two upstream fixes fell out of it — `_fallback_page_sections` and
`_toc_sections` now run to the next page's offset, so the page-join newline
belongs to the page it follows instead of becoming a one-character hole.

| | before | after |
| --- | --- | --- |
| documents losing material | **63 of 68** | **0 of 68** |

The loss was small per document (≈52 characters: the text between a
table-of-contents page and the next heading, and the tail after the last
heading) and structural: the cover/control block spanned to the first heading
*through* the ToC page the ToC pass also claimed, so those two sections
overlapped and the text after the overlap fell out. `--internal` on the fidelity
script now reports 68/68 faithful.

The internal corpus was re-materialized live against the new tiling
(`scripts/materialize_internal_corpus.py --corpus coding_task/v9_compliance/LSPG-CIP`):
68/68 documents, role census `OPERATIVE_PROCEDURE 1234, WORK_INSTRUCTION 783,
DOCUMENT_CONTROL 230, COMMENTARY 72, TABLE_OF_CONTENTS 65, DEFINITION 63,
INTERNAL_POLICY 60, EVIDENCE_SPECIFICATION 36, TRACEABILITY_ASSERTION 33`.

### 2.6 Deviation from the task text, recorded (R2)

P1.1 says both bounds in `core/cip_extract.py` go — the
`Requirements and Measures` restriction and the `\bViolation Severity Level`
terminator. **They are still there, deliberately, and the discard is gone
anyway.**

`_requirement_block`'s bounds are not a capture rule. They are what stops the
*pinned Part register* reading an `R1.` cell inside a VSL table as a
requirement. Stripping them while that register still runs manufactures garbage
Parts — a regression wearing a fix's clothes, which is R4 in a new costume. The
discard is removed from the product path by removing the path: regulatory
capture no longer routes through `cip_extract` at all, it routes through
`capture.py`, which has no bounds to remove. `cip_extract`'s module docstring now
says so and marks the module deprecated as the capture path; the register itself
retires in P10.2.

### 2.7 Migration 11

Additive, applied live, semicolon-free inside comments. The first attempt
violated R9 — `-- its own rows; these columns make the tiling queryable` split
into a bare `these columns …` statement and failed with
`sqlite3.OperationalError: near "these": syntax error`. The migration runner's
one-transaction-per-version discipline held: the store rolled back cleanly to
v10 with its original columns, which is the behaviour R9 exists to protect.

| change | table |
| --- | --- |
| `unit_kind`, `ordinal`, `char_start`, `char_end`, `heading_path` | `source_sections` |
| `ix_source_sections_ordinal`, `ix_source_sections_table` | — |
| `document_texts` (revision → captured coordinate space) | new |
| `source_table_cells` (section, row, col, column_name, text) | new |

One latent R9 hazard was found in the already-landed migration 9
(`-- A concept may span revisions;`) and left alone: it is applied everywhere and
its remainder happens to be a comment line, so it splits harmlessly.

### 2.8 Verification

| gate | result |
| --- | --- |
| `uv run pytest tests/unit/ -q` | **2011 passed, 4 skipped** (baseline 1991 + 20 new) |
| `uv run ruff check` / `ruff format --check` | clean |
| `uv run mypy portal/modules/compliance/core/capture.py` | clean |
| `tests/unit/test_spine_gates.py` | 6 passed (new wiki unit + manifest + two new probes) |
| store schema version | **11** |

**Rollback.** `git revert <sha>`; restore
`data/private/backups/pre-v11-20260916T023321Z.db`.

---

## §3 — P2 the Glossary becomes a corpus

### 3.1 Source and acquisition

NERC no longer publishes the Glossary as a PDF: `Glossary_of_Terms.pdf` and
`files/glossary_of_terms.pdf` both 302 to https://www.nerc.com/glossary-of-terms,
a page whose `window._model` payload carries **one structured record per term** —
the term, its acronym, the verbatim `definitionHtml`, status, region, docket
number, Board-adoption date, effective date and inactive date. That payload is
the authority, and it is strictly better than the PDF: the dates are the
Glossary's own, not parsed out of prose.

`nerc_source_sync` now acquires `glossary-of-terms.html` beside the standards
with the same append-only manifest and the same byte-hash UNCHANGED semantics,
under `role="glossary"`. Live run: **ACQUIRED, 473,538 bytes, `text/html`**, and
registered. A fetch failure is a named warning (*"defined terms will not
resolve"*) that never voids the rest of the bundle — covered by a test.

Term records are located **by shape, not by JSON path**, so a CMS reshuffle that
moves `pageModel.searchResults.items` fails loudly instead of silently yielding
zero terms.

### 3.2 Registration

| | |
| --- | --- |
| document | `NERC/glossary-of-terms` — *Glossary of Terms Used in NERC Reliability Standards* |
| `source_kind` / `jurisdiction` | `glossary` / `US` |
| sections | **330** (one per term, `extractor='nerc_glossary'`) |
| coordinate space | `document_texts`, same as any captured document |

A Glossary entry is now the same kind of addressable thing as a requirement Part
or an operator procedure section, in the same tables, ready to project in P4.

### 3.3 The seven terms, resolved live

`resolve_terms(repo, [...])` against the live store, `valid_at` defaulting to
today:

| query | resolved as | effective | inactive |
| --- | --- | --- | --- |
| `BES Cyber System` | BES Cyber System | 2016-07-01 | 2028-06-30 |
| `EACMS` | Electronic Access Control or Monitoring Systems | 2016-07-01 | 2028-06-30 |
| `PACS` | Physical Access Control Systems | 2016-07-01 | 2028-06-30 |
| `Protected Cyber Asset` | Protected Cyber **Assets** | 2016-07-01 | 2028-06-30 |
| `External Routable Connectivity` | External Routable Connectivity | 2016-07-01 | 2028-06-30 |
| `CIP Senior Manager` | CIP Senior Manager | 2016-07-01 | 2028-06-30 |
| `Cyber Asset` | Cyber **Assets** | 2016-07-01 | 2028-06-30 |
| `Frobnicating Widget Authority` | — | — | *"not a NERC Glossary term"* |

Each carries verbatim text, a section id and a date. The invented term does not
resolve, is not guessed, and is still returned naming itself.

### 3.4 Two things the live data forced, which a naive lookup would have got wrong

**The Glossary carries a term's future successor beside its enforceable
revision.** 2016-07-01 definitions with `inactive 2028-06-30` sit alongside
2028-07-01 successors from the virtualization project. A last-wins index served
`Protected Cyber Asset` as the **2028** definition — the wrong text, silently.
`resolve_terms` therefore selects by `valid_at` (default today), reports the
clock that excluded a revision, and names the other revisions in
`other_revisions` rather than hiding them. Verified both directions: today
selects the enforceable revision, `valid_at=2029-01-01` selects the successor.

**NERC renames headwords between revisions.** The enforceable definition is under
*Protected Cyber Assets* and its successor under *Protected Cyber Asset*; *Cyber
Assets* is plural while every CIP requirement says *Cyber Asset*. `normalise_term`
drops a trailing plural `s`, and the resolution names the headword it actually
matched (`matched_as`) so the inflection is visible, not silent. Checked against
all 330 live terms: exactly one bucket collapses two spellings
(`protected cyber asset`), and its two windows are **sequential**, so no two
distinct concepts are merged. An acronym is indexed only when every entry
carrying it belongs to one term — `EACMS` and `PACS` each appear twice, once per
revision of the same term, which is why they resolve; a genuinely ambiguous
acronym resolves to nothing rather than to a guess (covered by a test).

### 3.5 The deferral, resolved (P2.3)

`assessment_source.resolve_governing_bundle` now resolves
`definitions_disposition == "external_glossary"` instead of only recording it.
Live on `CIP-007-6 R2 Part 2.2`:

```
disposition: external_glossary
definitions: 7   (BES Cyber System, Electronic Access Control or Monitoring
                  Systems, Physical Access Control Systems, Protected Cyber
                  Assets, System, Cyber Assets, CIP Senior Manager)
```

Each carries `source: "NERC Glossary of Terms"`, its `section_id`, `revision_id`,
effective and inactive dates, and `matched_as`. Which terms a duty depends on is
decided by the **Glossary's own membership**, not by a vocabulary in the code: a
capitalised span is kept only when the Glossary carries it as a term. (`System`
appears because it genuinely is a NERC defined term.) An unresolvable term stays
in the payload, explicitly unresolved.

### 3.6 Verification

| gate | result |
| --- | --- |
| `uv run pytest tests/unit/ -q` | **2034 passed, 4 skipped** (+21 glossary, +2 sync) |
| ruff check / format, mypy on `glossary.py` | clean |
| live glossary registration | 330 sections, `source_kind='glossary'` |
| seven named terms | all resolve with verbatim text and a date |
| invented term | does not resolve, names itself |

Two existing tests changed behaviour rather than breaking: the hermetic sync
fixture now serves a Glossary page (the Glossary is a bundle component, so a
sync without it is incomplete), and the governing-bundle test now separates
graph-derived definitions from Glossary-derived ones instead of asserting an
exact list.

**Rollback.** `git revert <sha>`; acquired bytes stay (append-only).

---

## §4 — P3 symmetric materialization

`scripts/materialize_regulatory_corpus.py`, the twin of
`materialize_internal_corpus.py`. Migration 12 applied live (v11 → v12) against
`data/private/backups/pre-v12-20260916T030238Z.db`.

### 4.1 Live run

```
NERC/one-stop-shop                    lifecycle_registry   eff -           inact -           not captured — structured registry
NERC/glossary-of-terms                glossary             eff -           inact -            330 sections, 330 glossary terms
NERC/CIP-007-6                        regulatory_standard  eff 2016-07-01  inact 2028-06-30   278 sections,  80218 chars, cov 100.0%
NERC/CIP-007-6 implementation plan    implementation_plan  eff 2016-07-01  inact 2028-06-30   116 sections,  20627 chars, cov 100.0%
NERC/CIP-007-7.1                      regulatory_standard  eff 2028-07-01  inact -            141 sections,  34706 chars, cov 100.0%
NERC/CIP-007-7.1 implementation plan  implementation_plan  eff 2028-07-01  inact -             97 sections,  10982 chars, cov 100.0%
NERC/CIP-007-7.1 technical rationale  technical_rationale  eff 2028-07-01  inact -            211 sections,  62919 chars, cov 100.0%

hash-verified artifacts: 7
jurisdiction rows normalised: 13
jurisdictions now: ['internal', 'US']
```

Every date above is the workbook's, not a filename's. The workbook itself is
registered and dated but deliberately **not captured as prose** — its content is
the lifecycle facts, and those are already recorded structurally on every
revision they describe.

### 4.2 Store after P3

| jurisdiction | source_kind | documents | sections |
| --- | --- | --- | --- |
| US | regulatory_standard | 15 | 781 |
| US | glossary | 1 | 330 |
| US | implementation_plan | 2 | 213 |
| US | technical_rationale | 1 | 211 |
| US | lifecycle_registry | 1 | 0 |
| internal | procedure | 28 | 1,176 |
| internal | work_instruction | 26 | 979 |
| internal | plan | 5 | 309 |
| internal | policy | 1 | 68 |
| internal | process | 2 | 49 |
| internal | unknown | 1 | 38 |
| internal | evidence_specification | 5 | 17 |

Regulatory sections by `unit_kind`: prose 757, list_item 246, table_row 119,
table 51, figure_caption 1 — plus **362 with an empty `unit_kind`**, which are
the pre-P1 register-materializer rows on the `data/cip_pdfs/` revisions. They are
legacy, have no captured coordinate space, and P4 projects only captured
sections and reports the rest rather than pretending they resolve.

### 4.3 Both clocks, from the corpus rather than the register

`temporal_selection.select_document_effectivity` answers the two-clock question
from `document_revisions`' workbook-sourced lifecycle. Live, side by side with
the existing register path:

| valid_at | register: selected / future / historical | corpus: selected / future / historical |
| --- | --- | --- |
| 2026-09-15 | `6` / `7.1` / — | `6` / `7.1` / — |
| 2029-01-01 | `7.1` / — / `6` | `7.1` / — / `6` |

Identical. Also verified: at `2015-01-01` both revisions are `future`; with
`known_at=2020-01-01` both answer `UNKNOWN_KNOWLEDGE` (the store had not yet
acquired them); a revision with no effective date is `undated`, never read as
always-in-force (F02).

### 4.4 Identity, repaired

`canonical_identity` derives the logical id from the artifact's **role** and the
standard id in its name, with the version's own case preserved
(`CIP-002-5.1a`, not `5.1A`). Repairs applied to pre-P3 rows:

```
NERC/cip-007-6.pdf                        -> NERC/CIP-007-6
NERC/cip-007-7.1.pdf                      -> NERC/CIP-007-7.1
NERC/cip-007-6-implementation-plan.pdf    -> NERC/CIP-007-6 implementation plan
NERC/cip-007-7.1-implementation-plan.pdf  -> NERC/CIP-007-7.1 implementation plan
NERC/cip-007-7.1-technical-rationale.pdf  -> NERC/CIP-007-7.1 technical rationale
NERC/one-stop-shop.xlsx                   -> NERC/one-stop-shop
```

The first implementation of this merged `NERC/CIP-007-6 implementation plan`
into `NERC/CIP-007-6` — the version regex `^(cip-\d{3}-[\w.]+)` swallowed the
file extension, and the repair pass matched canonical ids as well as legacy
ones. Caught by reading the run's own output, rolled back to the pre-run
snapshot, and fixed twice over: the regex now reads the name's *stem*, and the
repair only matches ids that end in a file extension, so it can never merge a
component into the standard it belongs to.

### 4.5 A test was writing to the operator's live store

While reconciling the post-run census, the Glossary showed **331** sections
against **330** terms. The extra one was a `document_revisions` row whose
`alias_path` was
`/private/var/.../pytest-of-chris/pytest-1570/test_failed_refresh_preserves_0/glossary-of-terms.html`.

`Repository()` with no argument defaults to the production database, and the
hermetic NERC-sync test reached a code path that constructs one. A tmp_path
fixture's glossary page had landed in the operator's store as a real revision
with a real section, and nothing would have noticed but a count being one too
high.

Fixed at the root, not worked around:

* the leaked revision, its section, span and text were deleted;
* the sync tests stub Glossary registration, which is the store's concern, not
  the transport's;
* `tests/unit/conftest.py` gained an autouse fixture that redirects
  `Repository.__init__`'s and `MappingStore.__init__`'s **bound defaults** to a
  scratch file. The module constant `DEFAULT_DB_PATH` is left alone on purpose —
  it is the declaration that the two share one canonical file, and a test
  asserts exactly that.

A second defect surfaced with it: `store_capture` deleted prior sections by the
module-level `EXTRACTOR` ("docling") while inserting under
`captured.extractor`, so a Glossary re-capture would leave stale units beside
fresh ones. Now scoped to the capture's own extractor.

### 4.6 Verification

| gate | result |
| --- | --- |
| `uv run pytest tests/unit/ -q` | **2054 passed, 4 skipped** (+20 P3) |
| ruff check / format across `portal/ tests/ scripts/` | clean |
| `tests/unit/test_spine_gates.py` | 6 passed |
| store schema version | **12** |
| hash-match gate | 7/7 artifacts verified; mismatch and missing-file both covered by tests |
| jurisdictions in the store | `internal`, `US` — the split is gone |

**Rollback.** `git revert <sha>`; restore
`data/private/backups/pre-regulatory-20260916T030415Z.db` (the run takes its own
snapshot first).

---

## §5 — P4 one identity space

### 5.1 What changed

`core/section_index` emits the retrieval index **from** `source_sections`, at
section granularity, with `chunk_id = section_id`. No change to the shared Arrow
schema — the existing field carries the identity.
`compliance_retrieval.project_sections` writes those units through the same
stages as `ingest_document` (same embedder, same contextualize rule, same BM25
sparse arm) and differs only in where the units come from.
`ingest_folder` is marked **deprecated as the product retrieval path** in place.

### 5.2 The live projection

`uv run python scripts/project_compliance_sections.py`:

| corpus | eligible | projected | units | split | unprojectable | boundary complete | wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `operator_corpus` | 2,568 | 2,568 | 2,579 | 21 | **0** | **true** | 1,090.4 s |
| `nerc_corpus` | 1,173 | 1,173 | 1,173 | 0 | **0** | **true** | 161.9 s |
| `operator_notes` | 1 | 1 | 1 | 0 | 0 | true | 0.2 s |
| `conversation` | 0 | 0 | 0 | 0 | 0 | — (empty) | 0.0 s |

**Cost against the P0 extrapolation.** P0 measured 0.664 s/section on a sample
averaging ~750 characters and projected ~62 min for both corpora. The real
figure is **1,252 s (20.9 min) for 3,752 units — 0.334 s/unit**, about half the
extrapolation. The sample over-estimated because it drew evenly across the
store, which over-weights the long tail; the real population is dominated by
short table rows and list items. Recorded rather than quietly replaced.

### 5.3 Three populations, kept apart

A revision's capture is a *total* cover of that revision, so for a captured
revision the captured sections **are** the eligible population.

* **superseded** — pre-capture sections on a revision that now has one. They are
  a second extraction of the same bytes, which is the duplication this phase
  removes. Counted, not eligible, not silently dropped.
* **uncaptured documents** — revisions with no capture. Named by document, and
  `corpus_whole` is false while any remain, so a partial corpus cannot carry an
  absence claim about the whole jurisdiction.

The first dry run reported 2,636 internal sections unprojectable: the internal
materializer wrote sections and spans but **never persisted the document text**,
so no internal section could resolve to verbatim text. Fixed at the source —
`materialize_internal_corpus` now writes `document_texts` and the migration-11
positional columns, and the corpus was re-materialized.

### 5.4 A falsy-zero bug the tests caught

`int(entry["char_start"] or -1)` reads **0 as -1**. The first section of every
document starts at offset 0, so every document's first section was classified
unanchored and silently excluded: 68 internal and 6 regulatory sections, including
CIP-007-6's opening. Found by a unit test asserting the resolved text of a known
first section, not by inspection. Replaced with an explicit `_span_of`.

### 5.5 Identity, demonstrated live

| check | result |
| --- | --- |
| search hits resolving to a `source_sections` row | **50 / 50** across five queries |
| semantic query *"what is the intent of the security patch management requirement"* | top hits are `Rationale for Requirement R2` and the `Table R2` rows from `nerc_corpus` |
| lexical query *"at least once every 35 calendar days evaluate security patches"* | top hit is the **Part 2.2 table row**, followed by CIP-007-7.1's and the R2 VSL row |
| exact address `CIP-007-6 R2 Part 2.2` | resolved **as an address**, Part row first |

On the address path: a requirements-table row's verbatim text is
`2.2 | High Impact …` and never contains the string `CIP-007-6 R2 Part 2.2`, so
matching a full address lexically is luck. `compliance_search` now resolves an
exact regulatory address directly and labels those hits `match: "address"`,
which is stronger than hoping the sparse arm ranks it first. The sparse/dense
fusion is still what finds the row from its own words, as the third row above
shows.

### 5.6 The boundary is a fact (P4.6)

`acquire_exhaustively` reads the **whole declared population** rather than a
top-k window, and emits the receipt from the projection. Live on CIP-007-6's 278
sections:

```
complete receipt: True | candidates 278 | snapshot COMPLETE
boundary_proof_id: boundary-91b01811468966b66db1

withheld one section -> complete: False | omissions 1
boundary_proof_id: ''
```

Both directions. This is §0.4 closed: before it, every producer of a boundary
receipt in the tree was a test fixture or a replay script, and
`_boundary_proof_id` returned `""` on every production request.

### 5.7 Freshness is per corpus

One store-wide fingerprint made writing a single operator note mark the
**regulatory** index stale — false, and the fastest way to teach someone to
ignore the signal. `section_population_fingerprint(repo, jurisdiction)` and
`retrieval_projection_status` are per corpus, and a partial run carries forward
the corpora it did not touch. `--restamp` re-records a manifest only after
verifying the live table's `chunk_id`s equal the store's current units **row for
row**:

```
operator_corpus  expected 2579  live 2579  matches True
nerc_corpus      expected 1173  live 1173  matches True
operator_notes   expected    1  live    1  matches True
conversation     expected    0  live    0  matches True
projection status: FRESH (all four corpora FRESH)
```

---

## §6 — P5 addressability and the reading assembly

### 6.1 The tools

Seven new synchronous tools on the compliance MCP, none of which returns a run
id or starts a background job. `_SPAN_EXCERPT_CHARS = 180` is gone from this
surface: text is whole up to a caller-supplied `max_chars`, and truncation is
**stated** in the payload.

| tool | live result |
| --- | --- |
| `compliance_search` | both corpora, every hit resolved to a section, exact addresses resolved as addresses, both clocks honoured with exclusions named |
| `compliance_read` | `CIP-007-6 R2 Part 2.2` → 6 units, verbatim, page 9, effective 2016-07-01 |
| `compliance_links` | traversal with status, derivation and confidence on every edge |
| `compliance_timeline` | 5 revisions across CIP-007-6/7.1 and their companions, with the semantic delta |
| `compliance_coverage` | deterministic; named all four R2 Parts as having no link |
| `compliance_note` / `compliance_notes` | a note written in one call is retrievable in the next |
| `compliance_context` | see below |

`compliance_search` was the name of the raw kb-scoped passthrough; that is now
`compliance_kb_search`, and the route with it. The new tool is what an analyst
should use — it spans both corpora and resolves every hit.

### 6.2 `compliance_context` — the reading assembly

Live on **CIP-007-6 R2**, default 60,000-token budget:

| component | sections | tokens |
| --- | --- | --- |
| requirement | 9 | 936 |
| technical_basis | 11 | 1,874 |
| rationale | 2 | 73 |
| glossary | 7 | 317 |
| vsl | 13 | 656 |
| applicability | 6 | 510 |
| background | 10 | 822 |
| effective_dates | 2 | 14 |
| compliance_and_evidence_retention | 49 | 3,536 |
| version_history | 14 | 410 |
| implementation_plan | 116 | 5,156 |
| **total** | | **15,240 — nothing omitted** |

A requirement's whole neighbourhood, for a quarter of the budget. Each table row
carries its cells under their column names, so the Measure stays attached to its
Part:

```
Part               :: 2.2
Applicable Systems :: High Impact BES Cyber Systems and their associated: 1. EACMS; 2. PACS;
Requirements       :: At least once every 35 calendar days, evaluate security patches for ap…
Measures           :: An example of evidence may include, but is not limited to, an evaluati…
```

The first implementation emitted `measures` as a duplicate of `requirement` —
for a table-shaped requirement the Measures cell travels *inside* its Part row,
and a separate component just spent the budget twice. Now the Measures component
fires only for prose `M<n>` lead-ins, and the row carries its own cells.

### 6.3 Operator notes are sources

A note is a `source_documents` row, an immutable `document_revisions` row keyed
on its own bytes, and a `source_sections` row with a span — so it is citeable by
`section_id`, resolvable, projectable, and retrievable by search from the next
question onward. Written live against `CIP-007-6 R2 Part 2.2` and retrieved in
the next call.

### 6.4 Verification

| gate | result |
| --- | --- |
| `uv run pytest tests/unit/ -q` | **2110 passed, 4 skipped** (+39 for P4/P5) |
| ruff check / format, mypy on the new modules | clean |
| `tests/unit/test_spine_gates.py` | 6 passed |
| tools manifest / workspace reachability probe | `all_reachable:23` |

**Rollback.** `git revert <sha>`; `scripts/project_compliance_sections.py`
rebuilds the index from the store.

---

## §7 — P6 wiring the reader

Everything in this section was measured on the live stack with Docker **down**,
against the real CIP-007-6 R2 Part 2.2 neighbourhood. Transcripts:
`reports/compliance/seat_probe/`.

### 7.1 What the reader receives

`compliance_ask` hands the seat `compliance_context` output rendered as text:
every component labelled with what it is and where it came from, every passage
carrying its `section_id`, table rows broken out under their column names, the
operator's notes, and — when the budget dropped something — a section headed
*"omitted for budget — you have NOT seen these"*. Nothing is filtered, nothing
is marked ineligible to cite. The system prompt is 5 sentences and contains no
schema, no field list, no output shape and no instruction about how to weigh a
Measure against the Technical Basis. A test asserts those words are absent.

### 7.2 Four measurements that changed the design

**(a) Request-time `num_ctx` IS honoured on this transport.** P6.7 says to bake
context into the Ollama tag where the tag lacks one. Measured instead: a direct
`/api/chat` with `options.num_ctx: 32768` against
`mistral-small3.2:24b-instruct-2506-q4_K_M` (no baked `num_ctx`, 131k native)
produced `"context_length": 32768` in `/api/ps`, and `granite4.1:30b-ctx64k`
loaded at 32,768 — the request **lowered** a tag's baked 64k. **No tag was
baked**: the transport states the window per call and Ollama obeys. The
"request-time num_ctx is ignored" rule that motivated P6.7 belongs to the
pipeline/router path, not to this one. Deviation recorded rather than performed.

**(b) `CHARS_PER_TOKEN = 4` was wrong by 1.9×, in the dangerous direction.** The
runner's own log: `prompt processing, n_tokens = 29353`, for material the budget
had counted as ~15,700 tokens. Real ratio **2.16 chars/token** — dense
regulatory prose, and every passage carries a 29-character `section_id` that
costs about 12 tokens. The constant under-counted, so the window sized from it
was too *small*, and a slightly larger assembly would have been silently
truncated: the top-k keyhole returning by the back door. Now 2.1 (erring high),
and every call compares the estimate to the runner's real `prompt_eval_count`
and reports `context_fit` with observed chars/token, headroom, and an
`overflowed` flag. Window sizing also moved from next-power-of-two to next-4k:
33.5k rounded to 65,536 before, which on a 27B model is tens of gigabytes of
needless KV.

**(c) Material first, question last — worth more than any seat swap.** The
prompt originally put the question in front, so the first differing token of
every turn sat at position ~20 and the runner re-prefilled all 27k tokens.
Measured after reordering, glm-4.7-flash, same neighbourhood:

| turn | wall | prompt eval |
| --- | --- | --- |
| 1 — cold | 263.9 s | 27,176 tok in **214.7 s** |
| 2 — same question | 40.5 s | 27,176 tok in **0.1 s** |
| 3 — new question, same material | 30.4 s | 27,181 tok in **0.8 s** |

**268× less prefill on every follow-up.** Confirmed in the four-seat probe:
Qwen 406.5 s → 123.3 s → 152.7 s; granite 458.6 s → 39.1 s; mistral 324.3 s →
17.7 s. The first exchange of a session costs minutes; every one after costs
seconds. A test asserts the material precedes the question and that two
different questions share a >90% byte-identical prefix.

**(d) The machine thrashed before any of this was visible.** The first live
probe produced nothing for twenty minutes. Cause: `granite4.1:30b` at 32k
context is **36.4 GB resident**, and with the Docker stack up (21 containers)
swap hit **50.6 GB of 51.2 GB** and free memory 16%. Brought the stack down per
the standing rule; free memory went to 85% and the same call completed. Recorded
because "the model is slow" and "the machine is swapping" look identical from
the outside and have nothing in common.

### 7.3 Seat prefill throughput — why this is a sparse-mixture problem

12k-token prompt, 32k window, stack down:

| seat | prefill tok/s | gen tok/s | wall |
| --- | --- | --- | --- |
| `glm-4.7-flash:Q4_K_M-ctx64k` (MoE) | **244** | 34.2 | 58.1 s |
| `mistral-small3.2:24b` (dense) | 126 | 28.5 | 110.5 s |
| `Qwen3.8-27B` (dense) | 112 | 22.6 | 120.3 s |
| `granite4.1:30b` (hybrid Mamba) | 95 | 21.8 | 135.1 s |

What this workload costs is prefill over a long neighbourhood, and prefill
compute scales with **active** parameters. The two slowest seats are the two
non-MoE ones. `MOE_SEATS` in the probe script names the local A3B candidates for
a follow-up pass.

### 7.4 The seat, chosen by reading the answers

Three real questions, same neighbourhood, transcripts in
`reports/compliance/seat_probe/20260916T130058Z-seats.json`.

| seat | cold | warm | citations (Q1/Q2/Q3) | unresolvable |
| --- | --- | --- | --- | --- |
| Qwen3.8-27B | 406.5 s | 123–153 s | 9 / 7 / 7 | **0** |
| glm-4.7-flash | 276.2 s | 30–52 s | 7 / 4 / 2 | **0** |
| granite4.1:30b | 458.6 s | 39–168 s | 6 / 3 / 3 | **0** |
| mistral-small3.2 | 324.3 s | 18–55 s | 0 / 3 / 3 | **0** |

**Not one fabricated citation in twelve answers.** Citation fidelity did not
separate them, so the reading had to.

**Q2 decided it.** Asked whether evaluating every 30 days is stricter than the
35 the Part allows, **three of the four seats asserted that the operator's
procedure says thirty** — and it does not. `LSPG Security Patch Management
Procedure §3.3.1` says *"At least once every thirty-five (35) calendar days"*.
The thirty came from an operator **note**, elsewhere in the packet. Qwen3.8 was
the only seat that read the procedure itself, quoted it verbatim, and surfaced
the conflict between the written procedure and the recorded practice — a real
finding nobody asked it to look for. It also framed the 35 days correctly as a
maximum interval; granite called it a "minimum interval" and reasoned to the
right answer anyway.

`reading_seat` is therefore **Qwen3.8-27B**, recorded in
`config/compliance/council.yaml` with the argument. `glm-4.7-flash` is recorded
as the **fast alternate**: 3–5× quicker warm, and it made the sharpest single
observation of the probe — that the corpus holds the patch-evaluation *process*
but not the *record* an auditor would ask for — but it produced one of the three
misattributions.

### 7.5 Two verifier defects the probe exposed

**Unicode dashes silently voided correct citations.** granite4.1 cited six
sections and scored **zero**, because it wrote them with U+2011 NON-BREAKING
HYPHEN (`csection‑7ffb333ac44c2b9d3da3`). A checker that reads a correct
citation as a missing one reports a well-grounded answer as ungrounded. Dashes
are normalised before matching now; parameterised over six dash characters.

**Quantities were checked against the union of everything cited.** The original
check asked only whether a number appeared *somewhere* in the material, so
"the procedure evaluates every thirty calendar days [§3.3.1]" passed — the 30
was real, it was just in a different document. A quantity is now attributed to
the citation nearest it and checked **against that section**, and the three real
misattributions fall out automatically: with the fix, Qwen and granite come back
clean and mistral and glm are flagged for pinning "thirty calendar days" to the
regulatory row that says thirty-five. Two sub-bugs were fixed to get there —
`"thirty-five calendar days"` was matching as **"five calendar days"** (a
checker that reads 35 as 5 is worse than none), and `thirty` was not in the
number vocabulary at all. A claim with no citation within 300 characters is
reported as **unattributed**, not misattributed: that is a different observation
and calling it the other would be a false accusation. The result is a flag for a
human, not a verdict — attribution is positional and approximate at a paragraph
boundary, and the payload says so.

### 7.6 Reasoning effort, measured on THIS call site (P6.7)

`DEFAULT_EFFORT` was settled on a JSON alignment packet. A prose reading over a
27k-token bilateral neighbourhood is a different call, so it was re-measured.
Qwen3.8-27B, same packet, same question, one variable:

| effort | wall | thinking | answer | citations |
| --- | --- | --- | --- | --- |
| `false` | 432.0 s | 0 chars | **4,756 chars** | **7** |
| `low` | 449.8 s | 6,382 chars | **empty** | 0 |
| `medium` | 148.5 s | 6,258 chars | **empty** | 0 |

Not "slower for the same answer" as on the alignment packet — **no answer at
all**. The reasoning trace consumed the entire `num_predict` budget and the
content field came back empty. Reasoning stays off here, now for a reason
measured here. An empty answer is reported as `failed` with the budget numbers,
rather than travelling as a very short one.

### 7.7 The two §0 verifier defects, dispositioned (P6.4)

| defect | disposition |
| --- | --- |
| (a) `_verify_duties` checked context citations against `gov_ids` only, so a Measure cited as operator evidence passed with `verified_support=True` — the standard quoting itself as the operator's control | **FIXED by the new design.** `verify_citations` resolves **both** sides and labels what each citation IS: *"regulatory — a requirements table row"*, *"regulatory — Guidelines and Technical Basis (interpretive, the standard's own)"*, *"operator document — procedure"*, *"operator note — the operator's own recorded decision"*, *"a stored answer from an earlier conversation, not a fact"*. The standard cited as operator evidence is now visible as exactly that. No code disqualifies a citation. |
| (b) `_quantity_direction` chose its comparator with `"max_interval" if "every" in operand else "min_retention"`, so `"within 35 calendar days"` turned a 40-day shortfall into MORE_RESTRICTIVE → STRICTER → `unused_flexibility` | **DELETED with its cause**, not repaired. Deciding from the shape of a phrase which direction "more" points in is the prescriptive move §0 names. `DutyFinding.quantity_direction` remains on the dataclass, permanently empty, because the deprecated outcome map still reads it. The consequence is stated rather than hidden: that path now reports a genuinely weaker interval as ALIGNED, and its test says so and says why. |

### 7.8 Conversation as a corpus

Question, answer, citations, model, `num_ctx`, reasoning effort, elapsed,
`eval_count`, `prompt_bytes` and `load_duration` are retained in
`conversation_answers` / `answer_citations` and projected into the `conversation`
corpus as a `derived` source. A stored answer reports its own standing — *"one
analyst's notes pinned to the revisions it read"* — is marked **SUPERSEDED**
when a revision it cited moves, and says when an operator note on the same
subject outranks it. A correction is kept as a note *about the answer*; the
answer is never rewritten. Standing questions are recorded and runnable per
subject, which is what the on-ingest assessment is.

### 7.9 Correction — the earlier seat measurements were taken with the stack DOWN

Everything in §7.2(d) through §7.6 was measured with Docker stopped. **That was
a workaround, not a result.** The compliance module is a module *inside* Portal
5; a seat that only works when the product is switched off is not a seat, and
reporting its latency as the product's latency would be reporting a number
nobody can have. The stack was brought back up and the work redone against it.

Two things changed once the constraint was real.

**granite4.1:30b is excluded on footprint, before any question of quality.**
36.4 GB resident at 32k context cannot co-exist with 22 containers on a 64 GB
machine — that is what put it into 50.6 GB of swap and made the first probe
produce nothing for twenty minutes. Its reading was middling anyway, but the
footprint alone settles it.

**The packet, not the parameter count, was the failure.** 55% of the full
CIP-007-6 R2 Part 2.2 packet is the implementation plan (33%) and the
compliance/evidence-retention section (22%), while the requirement itself is 2%.
Scoping the packet to the question changes what a seat can do:

| seat | size | full packet (~29.9k tok) | focused `conformance` (~6.0k tok) |
| --- | --- | --- | --- |
| Qwen3.8-27B Q4_K_M | 18.8 GB | correct, 406 s cold | correct, 112 s cold / 55 s warm |
| glm-4.7-flash Q4_K_M (MoE) | ~19 GB | **WRONG** | **correct**, 28 s cold / 14 s warm |
| qwen3.5-abliterated 9B | **6.6 GB** | not tested | **correct**, 49 s cold / 23 s warm |
| granite4.1:8b | 5.3 GB | not tested | wrong |
| qwen3-vl:8b | 6.1 GB | not tested | wrong |
| Foundation-Sec-8B-Reasoning Q8 | 8.5 GB | not tested | wrong — and backwards |

glm-4.7-flash misread the operator's procedure when that sentence was one of 239
sections and read it correctly when it was one of 22. **Focusing the packet
bought more than buying a bigger model would have**, and it is the cheaper move
in every direction: less prefill, smaller seat, more headroom beside the stack.

Notable: `Foundation-Sec-8B-Reasoning` is the only model in the catalog trained
for this domain and it was the worst seat tested — it fabricated a citation, hit
the answer cap twice, and stated the operator's procedure says thirty when it
says thirty-five. Domain pre-training did not substitute for reading the packet.

### 7.10 Question-scoped packets (`profile`)

`compliance_context(profile=…)` and `compliance_ask(profile=…)`, measured on
CIP-007-6 R2 Part 2.2:

| profile | sections | est. tokens | carries |
| --- | --- | --- | --- |
| `full` | 239 | 29,904 | everything |
| `intent` | 35 | 6,467 | requirement, measures, technical basis, rationale, glossary, background |
| `conformance` | 22 | 6,013 | requirement, measures, glossary, applicability, **linked operator sections** |
| `audit` | 79 | 13,544 | requirement, measures, VSL, evidence retention, applicability, linked |
| `timeline` | 138 | 11,231 | requirement, effective dates, implementation plan, technical rationale, version history |

**Nothing infers a profile from the question** — that would be the prescriptive
move in a new place. The caller names it, `full` is the default, and everything
a profile leaves out is listed in `omitted` and rendered to the reader under a
heading that says *"NOT IN THIS PACKET — you have not seen any of the
following"*, with what each missing component would have answered.

That heading exists because of a measured failure. On the `intent` profile —
which deliberately excludes the operator's own sections — **all four small seats
answered "are we stricter than we need to be" confidently, from an operator note
alone, and none said it lacked the procedure.** The note misstates the
procedure, so all four were confidently wrong about the operator's own posture:
exactly the failure this module exists to stop. The omission block was a quiet
footnote; it is now the loudest thing in the packet. Choosing the wrong profile
is therefore a **correctness** decision, not a performance knob, and the report
says so rather than leaving it to be discovered.

### 7.11 The seats, and the rule that picks one

Recorded in `config/compliance/council.yaml` with the transcripts:

| role | seat | why |
| --- | --- | --- |
| `reading_seat` (focused profiles) | `glm-4.7-flash:Q4_K_M-ctx64k` | fastest measured (244 tok/s prefill against 95–126 for the dense and hybrid seats), correct on focused packets, 14–28 s per exchange |
| `reading_seat_full_packet` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | the only seat measured correct on 30k of material |
| `reading_seat_minimal` | `huihui_ai/qwen3.5-abliterated:9b-ctx64k` | 6.6 GB, correct on the discriminator, for a host with less headroom |

`_reading_seat(profile)` picks the full-packet seat when no profile is named and
the fast seat otherwise. End-to-end through the MCP tool **with all 22
containers running**: `compliance_ask(..., profile="conformance")` returned in
**35.4 s** with 5 citations, 0 unresolvable, the answer stored and projected.
Memory with the stack up and the seat resident: **56% free**.

### 7.12 The quantity check was narrowed, because it could not do what it claimed

§7.5 reported a per-citation quantity check that reproduced a hand finding. Run
across the wider transcript set it turned out to be unreliable **in both
directions on exactly the prose that matters** — an answer that correctly
contrasts two numbers:

* *false positive*: `"you are compressing the evaluation window by five days
  compared to the standard's 35-day maximum"` — correct arithmetic (35 − 30),
  flagged because "five days" is not in the cited note;
* *false negative*: granite4.1:8b wrote *"the operator's procedure evaluates
  every 30 calendar days"* — it says thirty-five — and cited nothing within
  range, so nothing was flagged at all.

Attribution is positional and prose is not. P6.3 says verify citations and
**adjudicate nothing**, so the field was renamed `quantity_review_pointers`, now
carries the sentence it points at, and is documented as a pointer for a human
rather than a judgement. Citation *resolution* — which is reliable, and which
caught a fabricated id from Foundation-Sec-8B — is unchanged.

### 7.13 Verification

| gate | result |
| --- | --- |
| `uv run pytest tests/unit/ -q` | **2135 passed, 4 skipped** (+81 for P6) |
| ruff check / format, mypy on the new modules | clean |
| citation resolution, both directions | a real citation resolves and is labelled; a fabricated one is named; six dash spellings resolve |
| latency per exchange, **stack up, focused packet** | **14–35 s warm**, 28–112 s cold; recorded per call with the prefill/generation split |
| co-residency | `compliance_ask` end to end with all 22 containers running: 35.4 s, 56% memory free |
| seat choice | argued from transcripts in `reports/compliance/seat_probe/`, recorded in `config/compliance/council.yaml` |

**Rollback.** `git revert <sha>`; delete `conversation_answers`,
`answer_citations` and the `conversation` projection.
