# PROGRAM_RETRIEVAL_AND_COMPLIANCE_V1 — closeout

Tracked completion record for the review-cycle program whose working doc lives at
`coding_task/PROGRAM_RETRIEVAL_AND_COMPLIANCE_V1.md` (git-ignored operator area).
Closed 2026-09-03.

## All four tracks landed on `main`

| track | commit(s) | result |
|---|---|---|
| **T1** `TASK_RAG_COMPOSITION_SEAM_V1` | `3de59b6c`..`1f468724` (9) | Retrieval substrate extracted to `portal/platform/retrieval/`; `rag_multimodal` is one composition, **byte-identical** (function-level + live-KB parity, 30 vectors full float64, 10 queries, ingest response identical vs pre-seam `3de59b6c`); O8 auto-RAG contract fixed; stage-set stamp (check `HD`); compliance composition scaffolded. |
| **T3** `TASK_COMPLIANCE_ENGINE_V1` | `5d1536cf` | ~~152-node~~ bitemporal CIP register (validity-time, not observation-time); `effective_parts` predicate filter; authority tiers 0–4 + `COMPLIANCE_CONFLICT` (emitted, never reconciled); `MappingStore` (propose/approve, override rate); applicability `[GATE]`; coverage-by-enumeration (examined ≠ substantively_resolved, Bully GP); planted corpus **~~8/8~~ control classes**, **Full-Gap recall 1.000**, **citation resolution 1.000**, false-covered 0; `nerc_cip_currency` MCP tool (Phase 8). **Superseded by `TASK_CIP_REGISTER_COMPLETENESS_V1` (P1–P6): the register was materially incomplete and its `n_missing` was a fidelity round-trip, not a completeness check — now 254 nodes / 232 Parts, 0 document-declared holes, 11 control classes. See `reports/compliance/REGISTER_COMPLETENESS_V1.md`.** |
| **T4** `TASK_COMPLIANCE_CHANGE_PIPELINE_V1` | `53e36216` | `register_diff` — typed 8-change-type Part diff; `LANGUAGE_CHANGED` sub-typed (modality/timeline/evidence/substantive/**cosmetic**); cosmetic never raised as an obligation change, counted separately; `RENUMBERED` shift-insert detection. `change_pipeline` — impact traversal (AssetScope-gated), `expire_mappings` (successor `NEEDS_REVIEW`, **verdict never inherited**), prospective analysis (all rows `prospective:true`), `draft_revisions` **specification-only `[GATE]`**. ~~`CIP-003-8 → CIP-003-9`: 2 substantive + 11 cosmetic; Attachment-1 Section 6 = documented false negative.~~ **Re-run on the corrected register (`TASK_CIP_REGISTER_COMPLETENESS_V1` P4): 22 rows, 6 substantive, 16 cosmetic; Section 6 raised as `PART_ADDED`, false negative resolved (1 → 0).** |
| **T2** `TASK_RAG_SUBSTRATE_MIGRATION_V1` | `4ef9278c` `f9da32b4` `f9ae1ba5` | O1–O7, O10 all closed; the compliance/OT KB migrated with per-query evidence; the §4 void verdicts re-decided. Full rollup: `reports/retrieval/SUBSTRATE_MIGRATION_V1.md` + `reports/retrieval/substrate_migration_v1_data/` (13 per-query JSONs). |

## Open findings O1–O11 — resolution

| # | resolution |
|---|---|
| O1 `matplotlib` undeclared | **FIXED** T2 P1 — new `cad` extra; GL→matplotlib fallback proven with a forced failure. |
| O2 text hits carry no page | **FIXED** T2 P2 — `char_start`/`char_end`/`page` returned; `page` real under docling, `null` (never guessed) otherwise. |
| O3 visual hit ships placeholder as content | **FIXED** T2 P2 — `text:null`, `content_available:false`, `locator`, `pointer_note`; router `_extract_snippets` skips it. |
| O4 no sparse arm | **FIXED** T2 P3.3 — `create_fts_index` at ingest, `_bm25_rows` RRF-merged; lexical-decoy set added first; decoys 7/8→8/8, prose r@1→1.000, 0 decoy FP. |
| O5 docling `HybridChunker` unused | **FIXED** T2 P3.2 — `read_document` returns the `DoclingDocument`; `chunk_docling` carries `prov.page_no` + heading path. |
| O6 `contextualize` unused | **FIXED** T2 P3.4 — env-gated, default off; validation check `HE` FAILs on any security-readable KB; seeded-violation test. |
| O7 visual arm indexes every page | **FIXED** T2 P3.1 — `RAG_VISUAL_SCOPE=figures`; 435→16 visual rows, zero recall cost. |
| O8 auto-RAG contract broken | **FIXED** T1 P1 — default off (gate answered), correct `top_k`+`kb_id`, error ≠ miss. |
| O9 nominal `claims:` probe | **FIXED** T1/T3/T4/T2 — real bindings: `retrieval.stages`, `retrieval.stage_set`, `retrieval.compositions`, `compliance.register`, `compliance.change_types`. |
| O10 `check_updates` drift advice | **VERIFIED ALREADY FIXED** at HEAD (`TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 D1`) — direction-aware, refuses `uv sync` when venv is ahead, `except` sets status. |
| O11 compliance context split 8192/24576 | **NOT DIRECTLY ADDRESSED** — the engine is deterministic keyword-routed (`classify_intent`/`route`), not dependent on a large in-context prompt; a measurement against a real conversational multi-doc compliance prompt is a follow-up (§ below), not a blocker. |

## Void conclusions (§4) — re-decided on the compliance eval corpus

- **`VL_TEXT_GATE` / τ = 0.72** → **keep τ = 0.72 on a docling KB, with BM25.** O7
  confirmed (435→16 visual, 96% were double-indexed prose). On the figure-scoped
  docling index the τ *range* does not transfer (0.80 → prose r@1 0.50) but the
  shipped value 0.72 keeps prose intact (0.938, → 1.000 with BM25). `unified` was
  tested and loses (0.938 prose, 7/8 decoys — `search_unified` has no BM25 arm).
- **`structured` lost to `fixed`** → **void; docling's `HybridChunker` wins prose
  decisively** — prose r@1 0.812 → 0.938, r@5 0.938 → 1.000, `prose-cip-07`
  ("how does CIP-002 categorize BES Cyber Systems", the realignment doc's "not in
  the top 5 at any τ") → **rank 1**.
- **S0 off "because diagram r@1 = 1.000"** → **stays off for this KB.** The
  remaining diagram-lane loss is a ranking problem, not answerability: every
  synthetic figure doc's page-2 "See the `<name>` drawing" caption outranks the
  figure image in every fusion mode (figure page always r@5 = 1.000). This is a
  synthetic-corpus artifact — the `diagram_only` metric refuses a
  right-file/wrong-modality hit.

Definition-site comments in `fusion.py` and `chunking.py` corrected accordingly.

## Gates — all delivered

- **T1** — auto-RAG KB: operator answered **leave off**.
- **T3** — asset applicability scope: report-not-choose (`gate_presentation()`),
  scope is operator input, never inferred.
- **T3** — `FULL` without SME: resolved by the mapping store (system only
  proposes; an approved row is authoritative).
- **T4** — drafted revisions: specification-only mode only; (b)/(c) raise
  `NotImplementedError`. Reported not chosen.

---

## Follow-up for offline review — data points still needed

None block the program.

### 1. General RAG — 13 unmigrated consumers
Only the compliance/OT KB was migrated with evidence. The other kb_search
workspaces have **no ingested KB and no query set on this machine** (local
LanceDB: one test KB `kb1`; docker volume: `kb_smoketest`). Each needs, before
its substrate can move: (a) its persona's source corpus staged, (b) a labelled
query set, (c) a per-KB run of the T2 protocol (parity → per-stage re-ingest →
per-query re-measure → adopt/revert, stamped). Check `HD` already WARNs on any
KB still on the pre-P3 substrate. The compliance KB's adopt decisions
(figure-scope + docling + BM25 + `text_gate` τ 0.72) are **not** transferable —
a security corpus must keep `contextualize` off (gate `HE`).

### 2. Diagram-lane retrieval + S0 — need a real figure corpus
The `diagram_only` metric is unscoreable on the synthetic corpus (caption-text
artifact above). Needed: real P&ID / HMI / one-line-diagram PDFs with no "see
the drawing" caption text and queries answerable only from the image. On that
corpus re-run: the τ decision, `text_gate` vs `unified`, and **S0 figure
transcription** (the answerability question + whether the ~5–8 s/page ingest cost
is justified). Until then S0 stays off and the diagram-lane verdict is
provisional.

### 3. `unified` fusion + BM25
`search_unified` has no BM25 arm (`_bm25_rows` is wired only into `rrf_fuse`), so
the `unified`-vs-`text_gate` comparison was unfair to `unified`. If the
threshold-free path is wanted (cleaner, cannot silently regress), add a BM25 arm
to `search_unified` and re-run on a docling KB.

### 4. Compliance — O11 + end-to-end persona eval
- **O11**: measure the `auto-compliance` persona answering a conversational
  multi-document prompt ("does our procedure meet CIP-007-6 R2, and what changed
  in -9") across the standard + policy + register in one turn, against the
  `8192`/`24576` split.
- **End-to-end eval**: `rag_retrieval_eval.py` scores `kb_search` alone. A
  harness that scores the *persona's answer* (grounding accuracy, citation
  resolution, gap correctness) against the planted corpus + the CIP standards
  together — the R3 "does our procedure meet the standard" question from
  `RAG_COMPLIANCE_QA_REALIGNMENT_V1` — is the real acceptance test and does not
  yet exist.
- **Multi-turn / conversational retrieval** (R4) remains an absent capability —
  `kb_search` and the engine are single-shot.

### 5. Operational
The `:8942` VL retrieval server wedges after ~2.5 h of continuous embed+rerank
load (health still answers; the worker deadlocks on one in-flight request).
`launchctl kickstart -k gui/<uid>/com.portal5.vl-retrieval` clears it in ~5 s. A
migration campaign that runs many back-to-back evals must restart the VL server
between phases and checkpoint per-stage outputs. Root cause not investigated.
