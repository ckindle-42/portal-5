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
