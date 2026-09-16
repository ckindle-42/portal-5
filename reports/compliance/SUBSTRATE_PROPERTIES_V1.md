# SUBSTRATE_PROPERTIES_V1 — the four properties, declared then built

Base `114c3918`. Every number below is from a live query or a live run on this
machine (`reports/compliance/SUBSTRATE_PROPERTIES_V1_measurements.json` holds
the raw measurement output; the embedder ran at `:8917` throughout).

`core/__init__.py` named four properties on the day the module was created and
said of them: *"Not a RAG chatbot. Four properties, none a retrieval
parameter."* At base HEAD none of the four existed. This file built them. File
B (agentic reader), C (seat as a scored workspace binding) and D (verdict
retirement) wait on exactly this.

---

## §1 — The four properties, before and after

### Property 1 — temporal validity filters **before** ranking

| | state |
| --- | --- |
| before | The only `.where(` in the module was the docstring's own claim. The projected index row carried nine columns — no `jurisdiction`, `logical_id`, `revision_id`, `source_kind`, clocks or supersession — so every filter ran as a SQLite lookup **after** retrieval: a sieve that can shrink, never target. A blind top-15 across superseded revisions could return zero after sieving while the governing revision sat at rank 11. |
| after | Every projected row carries **11 predicate columns** copied from the canonical store (`section_index.PREDICATE_COLUMNS`, `build_plan`); `store.text_table` grew an additive `schema=` parameter so the compliance composition's tables carry them and every other consumer's schema is byte-identical. `pipeline.search(..., where="")` and `fusion.fuse(..., where="")` push a predicate into the dense arm, the BM25 arm, and the visual arm where its schema can express it — reported as not applied where it cannot (`FusedWithFilter.filter_report`). `compliance_mcp._search_predicate` builds the clock clauses: `(effective_from = '' OR effective_from <= V) AND (effective_to = '' OR effective_to > V)`, the same for `recorded_*` at `known_at`, and **`is_superseded = 0` when no clock is given**. The post-filter sieve is gone; `excluded` now means "does not resolve in the store" (an integrity signal) and the payload carries `filter_applied`, `filter_notes` (UNKNOWN_KNOWLEDGE keeps its name) and `filter_report`. |

Evidence: `tests/unit/test_compliance_search_pushdown.py` — 8 tests over a real
store, a real projected LanceDB table and the real tool; **6 of 8 fail on the
pre-P3 code**, including both superseded-competition regressions. Live: the
clause `(logical_id LIKE '%CIP-007-6%' …) AND is_superseded = 0` narrows
`nerc_corpus` from 1,903 rows to 394 **below ranking**; live `compliance_search`
with `valid_at=2026-09-16` returns the Part 2.2 row itself in the top 3 with
`filter_applied` naming the clause that ran.

### Property 2 — authority tiers have precedence; contradiction is retrievable

| | state |
| --- | --- |
| before | `tiers.py` emitted `COMPLIANCE_CONFLICT` into `coverage.py` — a cell file D retires — and `intentionality.py`/`ingest.py`. `reader.py` and `reading_assembly.py` referenced tiers zero times: the reading path could not see authority, so the property died with the verdict engine. |
| after | A section always arrives labelled with its authority: `tiers.recorded_tier` resolves the ingest sidecar's recorded tier, then the module's declared doc-class table on an **exact** hit, else `""` — untiered, visibly, never defaulted to Tier 3 or lent a Tier 4. It projects as the `authority_tier` column, rides `_provenance` on every `compliance_search` hit and `compliance_read` unit, and rides `_cite` on every assembly section. Contradiction is a retrievable fact: `reading_assembly.conflicts_for_requirement` keeps `tiers.detect_conflicts` unchanged (both spans, both tiers, both citations, never reconciled) and re-homes the guards that made it true on the live corpus — the requirement's own rows are the only standard-side spans (the standard quoting its own Measures fires nothing), and the topic-overlap gate survives `coverage.py`'s retirement. It is reachable three ways: the `compliance_conflicts(ref)` tool, the assembly's `conflicts` component, and `_DISPATCH`. |

Evidence: `tests/unit/test_compliance_authority_surfaces.py` — policy (tier 2)
vs work instruction (tier 3) incompatible cadences produce one conflict with
both section ids and no reconciliation; the Measures false-positive shape
produces zero; an untiered document projects `""` and is named in
`untiered_sections`; every search hit carries a tier field.

### Property 3 — gaps come from enumeration, not from asking

| | state |
| --- | --- |
| before | `assessment_source.acquire_exhaustively` read the whole declared population and emitted a real boundary receipt — with **zero production callers**. |
| after | The primitive has a home of its own: `enumeration.declared_population(repo, *, jurisdiction, scope_sections=None)` returns the resolved population plus the boundary receipt. `acquire_exhaustively` is reduced to a caller of it (behaviour preserved — all 43 section-index/assessment-source tests pass), and it is the ONE implementation file B's closure and file D's `compliance_orphans` consume. `assess_part` was deliberately **not** touched — that path is file D's to retire. |

### Property 4 — settled mappings are the evaluation set

| | state |
| --- | --- |
| before | `mapping_store.py` declared every approved mapping a labelled example. Nothing used them that way: no eval, bench or scorer treated them as ground truth. Every model decision hand-read transcripts — hence "provisional" forever. |
| after | `core/evaluation.py`: `labelled_examples(repo)` exports the settled `requirement → section` mappings with who approved, when, and whether it was a correction — plus explicitly rejected mappings as labelled negatives; `as_eval_set` is the shape file C binds; `score_reading` measures **citation behaviour only** — recall, precision over labelled citations with unmapped ones reported `unlabelled` (never wrong), rejected-mapping avoidance flagged separately by name, closure honesty carried as `None` when absent. An empty labelled set returns `honest-BLOCKED` naming the shortfall, never a zero. Nothing in `portal/` outside `evaluation.py` imports it — a test walks the tree and enforces it. |

Evidence: `tests/unit/test_compliance_evaluation.py`, 12 tests.

---

## §2 — The measurements (P6.2)

### 2.1 The superseded-competition measurement — the size of the defect

Six live queries against the projected index (4,483 rows in the three product
corpora), unfiltered dense top-15 — the pre-P3 shape:

| measure | value |
| --- | --- |
| superseded rows occupying pre-filter top-15 slots | **1 of 6 queries** (the ESP-cadence query pulled an old Glossary revision) |
| queries whose governing section fell outside the pre-filter top-15 entirely | **0 of 1 locatable-target query** |

Stated plainly: on this corpus the cost so far is **one wasted slot in one of
six queries, and no lost governing section**. The mechanism-level regressions
(`test_the_governing_text_survives_near_duplicates_filling_the_keyhole`) show
what the shape does at top_k=1–3; the live corpus is young — the CIP family
scale-up is 3 of 36 — and the old Glossary revision (330 rows) is its only
live superseded population. The defect is small *today*; `is_superseded` keeps
it from growing with every daily sync.

### 2.2 Recall at top-k ∈ {5, 10, 15}, with and without pushdown

The §P5 mapping ground truth is **empty**: 0 settled sections across 1,427
proposed rows and 1 revoked. Recall against it is therefore `honest-BLOCKED`,
and the measurement ran against the hand-judged probe discriminator
(READING_SEAT_RESEARCH_V1 §2.1 — the three sections that decide Q2: the Part
2.2 row, procedure §3.3, the operator note; labelled *hand-judged,
provisional*):

| k | without pushdown | with pushdown | superseded in top-k |
| --- | --- | --- | --- |
| 5 | 0.667 | 0.667 | 0 |
| 10 | **1.000** | **1.000** | 0 |
| 15 | 1.000 | 1.000 | 0 |

**The default is set by that number and recorded: `top_k = 10`** — recall
saturates at 10 and the 5-slot point is short of the note. This must be
re-measured on the mapping ground truth once file C's WFE arm exists and an
SME approves real mappings; it is provisional in exactly the way the seat
choice was, except that the number behind it is written down.

The 15s on the retire-in-file-D paths (`propose.resolve_candidates`,
`assessment_source.build_assessment_request`) are left alone by design.

### 2.3 Scorer validation against the four hand-judged transcripts

| measure | value |
| --- | --- |
| transcripts | 4 (`*-seats.json`) |
| hand-judged answers | 45 |
| scorer verdicts: scored / honest-BLOCKED | **0 / 45** |
| blocker | `requirement 'CIP-007-6 R2 Part 2.2' carries no settled section mapping — nothing to recall against` |

The scorer does not disagree with the hand judgment — it cannot score anything,
and says so, by name, 45 times. That is §0's finding converted into an
instrument output: the module declared its evaluation set and never wired it,
so the ground truth for the seat question is still zero rows. File C now has
the tool that turns an SME's next approval into a score.

### 2.4 Untiered documents §P4.1 surfaced

**28 of 146 documents** carry no recorded tier: 24 `technical_rationale`, plus
`glossary`, `lifecycle_registry`, the operator note, and the one derived
answer. All are visible as `authority_tier = ""` on every row they project —
never silently Tier 3, never lent Tier 4. Naming them is the input to a
decision (record tiers for the rationale documents or leave them untiered by
policy); nothing in this file made that decision.

### 2.5 P3.3 — the superseded population, and the open item it settles

The HEAD commit recorded that `glossary_index` reads only the latest revision,
so a superseded revision's sections stay projected and searchable but
unreachable through the glossary path — unbounded growth under a daily timer.
**Resolved, not by deciding the larger question, but by the flag:** superseded
rows stay in the index (history is answerable — 330 old-Glossary rows are
projected right now) and are excluded by default (`is_superseded = 0` in the
default predicate), so they cannot spend top-k slots against governing text. A
caller who wants history says so (`valid_at`/`known_at`, or search the corpus
raw). The daily timer now grows the index without growing the default result
space.

---

## §3 — The shared retrieval library is unharmed

The acceptance condition of P2, proven three ways:

1. **Byte-identical no-filter results.** A deterministic fixture (real
   LanceDB, hash-vector embedders, both arms) produced identical JSON — ids,
   order, fused scores, payload keys — from pre-change and post-change code
   (`diff` empty across four searches and `search_all`). The same expectation
   is pinned permanently in `TestNoFilterResultsAreUnchanged`.
2. **Every existing caller, unchanged.** `pipeline.search` /
   `fusion.fuse` callers: `rag_multimodal._search`/`_search_all`,
   `compliance_retrieval.search`, `propose.py:413` — all positional, all
   unaffected by a keyword-only `where=""`. `uv run pytest tests/unit/ -q -k
   "retrieval or rag or fusion or pipeline or bully"`: **336 passed** (the one
   failure was the spine-coverage manifest, regenerated with the unit that
   documents `predicates.py`; it re-passed). Full compliance suite: **935
   passed** post-P4.
3. **One seam, both consumers.** The Bully's inline `key = 'value'` builder is
   replaced by `predicates.build` (`organ.py:_search_table`), behaviour
   preserved for its str/int filters (its tests pass untouched), and quotes are
   now escaped rather than interpolated. The injection test: a `standard`
   argument of `LSPG/doc0' OR 1=1 --` stays a quoted literal, matches nothing,
   raises nothing.

Rollback evidence is in the task file; the phases are six commits, one per
phase.

---

## §4 — Bugs found by reading live output, each with its test

| # | defect | evidence | test now covering it |
| --- | --- | --- | --- |
| 1 | The four declared properties did not exist; the docstring described an intention as an architecture | §0 of the task file, verified at HEAD: one `.where(` in the module, and it was the docstring's | the four suites this file shipped (`test_compliance_search_pushdown.py`, `test_compliance_authority_surfaces.py`, `test_compliance_evaluation.py`, `test_compliance_section_index.py` additions) |
| 2 | `recorded_from` is stored as a full timestamp; left whole, `"2026-09-05T13:…" <= "2026-09-05"` is **false** — a revision would have been invisible on its own recording day | census of `document_revisions.recorded_from`: 149/149 full ISO timestamps | `test_clocks_are_date_shaped_with_explicit_open_bounds` (P1) |
| 3 | `is_superseded` had no live population to mark: `plan.superseded_sections` are pre-capture duplicates that are never projected, while the actually-searchable superseded population (a document's non-governing revisions) was unmarked | live store: 330 old-Glossary rows searchable with no marker; `NERC/glossary-of-terms` the only multi-capture document | `test_a_replaced_revision_is_flagged_governing_is_not` (P1); default predicate `is_superseded = 0` (P3) |
| 4 | A predicate the visual arm cannot express would have been silently dropped there — a fused list where half the candidates ignore the filter | by construction; the task names it as the failure P2 exists to prevent | `test_an_inexpressible_visual_predicate_is_reported_not_silently_skipped` (P2) |
| 5 | `_arm_has_column` initially scanned quoted literals as identifiers (`'US'` looked like a column), so any value containing an identifier-shaped token would have been misreported as inexpressible | caught by the P2 tests on first run | `test_a_filter_hits_dense_bm25_and_visual_when_expressible` (P2; literals stripped before the scan) |
| 6 | Edge endpoints have two recorded shapes — bare `section_id` and `mapping_store`'s `{document}::{section_id}` — and the reading path resolved only the raw value; on the live store **every** `::`-shaped edge resolved to nothing (0 tails resolvable as stored, 46 bare-id edges working) | live query over `relationship_assertions`: no `::`-tail resolves as stored | `test_a_doc_colon_colon_section_edge_resolves_to_its_section` (P6) |
| 7 | The mapping ground truth is empty — 1,427 proposed rows, 1 revoked, **0 approved** — so the declared evaluation set never existed | `evaluation.labelled_examples` on the live store; scorer validation §2.3 | `test_an_empty_labelled_set_is_honest_blocked_never_zero` + `test_an_unknown_requirement_is_honest_blocked_naming_the_shortfall` (P5) — the shortfall is now named by the instrument, not by a human |

---

## §5 — Where this leaves the module

The founding docstring now names an implementation for every property it
claims — that rewrite is itself the acceptance test for this file: a property
without a named implementation does not belong in the docstring. What file B
can assume: a search that can scope a query (and say what it scoped), a reading
whose every passage arrives labelled with its authority and its known
contradictions, a population primitive that makes absence claims checkable,
and a ground truth that grows every time an SME clicks approve. What file C
waits on is no longer code — it is the first approved mapping.
