# RAG Compliance Q&A — Realignment (TASK_RAG_COMPLIANCE_QA_REALIGNMENT_V1)

**Status:** OPEN — written for offline review, not yet scheduled
**Raised:** 2026-09-02
**Predecessor:** `TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2` (closed; `20676d50`)
**Evidence:** `reports/runtime/HARDENING_V2_P4_MEASUREMENTS.md` §P9, §P10 ·
`tests/fixtures/rag_eval_corpus/retrieval_eval_baseline.json` ·
`KNOWN_LIMITATIONS.md` P5-VL-RETR-002

---

## 1. The goal, as stated

> *"Ideally we'd give it a set of 'current' NERC CIP standards, also our policy
> and procedures to meet said standards and inquire about each, all are PDFs
> varying in length, the system overall should be able to handle that and in
> turn conversations about said documents."*

Four requirements are embedded in that sentence:

| # | Requirement | Status |
|---|---|---|
| R1 | Answer questions about a **standard** | partly measured |
| R2 | Answer questions about **our policy/procedure** | partly measured |
| R3 | Relate the two — does our procedure **meet** the standard | **not measured, not expressible by the current metric** |
| R4 | **Conversations** — multi-turn, follow-ups | **absent capability** |
| R5 | **PDFs varying in length** | text arm OK; visual arm untested past 25 pages |

## 2. The problem

The retrieval work to date optimised `VL_TEXT_GATE` (τ) against an evaluation
that does not represent this use case. The τ result is internally valid and
externally misleading.

### 2.1 The query set is weighted to the wrong document class

21 of 37 scored queries are `diagram_only`, and **all 21 target synthetic
2-page PDFs generated for the eval** (P&IDs, HMI screenshots, relay settings,
plot plans, a locked-valve schedule).

The real corpus is 26 documents — 16 NERC CIP standards, 9 OT policies, 1 NIST
slice — overwhelmingly **prose and tables**, 10 of them longer than 25 pages
(`cip-003-8` 59pp, `cip-007-6` 51pp).

`VL_TEXT_GATE` exists precisely to trade prose recall against diagram recall.
It has therefore been fitted to a 57%-synthetic distribution that production
will not reproduce.

### 2.2 The metric cannot express R3

`scripts/rag_retrieval_eval.py::_rank_of` scores a hit when **one**
`target_file` appears at rank ≤ k.

A compliance question — *"does our procedure satisfy CIP-007-6 R2?"* — requires
the **standard and the policy retrieved together**. A result returning five
chunks from the standard and nothing from the policy scores **1.000** and is
useless to the user. Source diversity is neither measured nor enforced anywhere
in the fusion path.

This was visible earlier and misread: when two documents both ranked plausibly
for `prose-cip-01` / `prose-cip-05`, `also_accept` was added and the case
recorded as query-set ambiguity. It was R3 showing through the metric, and the
fix suppressed the signal.

### 2.3 The most representative query in the set is the worst result

> `prose-cip-07` — *"How does NERC CIP-002 categorize BES Cyber Systems as high,
> medium, or low impact?"*

The archetypal compliance question. Its answer is **CIP-002 Attachment 1, a
table**.

| configuration | rank of `cip-002-5.1a.pdf` |
|---|---|
| structure-aware chunking (docling) | **1** |
| `unified` fusion, text depth 3 | **1** |
| early builds | 3 |
| fixed chunking (docling 2.124) | 5 |
| **fixed chunking, shipping stack** | **absent from top 5** |

**Not an extraction failure.** `cip-002-5.1a.pdf` contributes 121 chunks; 23
mention "Attachment 1"; "High/Medium/Low Impact Rating" each appear in 3. The
content is indexed and the query uses near-verbatim terminology. It loses to
`cip-007-6` (system security management) and `cip-009-6` (recovery plans), both
topically wrong.

It has **degraded silently across builds** — rank 3 → 5 → absent — hidden
because aggregate prose r@5 stayed 1.000 until the final run.

### 2.4 Two rejected options are the two that fix it

| option | rejected on | but |
|---|---|---|
| structure-aware chunking | aggregate prose r@1 0.875 → 0.750 | `prose-cip-07` **rank 1** |
| `unified` cross-encoder fusion | aggregate diagram r@1 0.619 vs 0.714 | `prose-cip-07` **rank 1** at depth 3 |

Both rejections were made on an aggregate dominated by synthetic diagram
queries, and neither was checked per-query against compliance-representative
ones. **Both verdicts are provisional and must be re-run against a corrected
query set before being treated as settled.**

### 2.5 R4 is an absent capability

`kb_search` is single-shot and stateless: `{kb_id, query, top_k}` in, ranked
chunks out. There is no query rewriting, no ellipsis/pronoun resolution against
prior turns, no dedup against chunks already shown. **Zero of the 37 eval
queries are follow-ups.**

Architectural note: Rule 4 makes the Pipeline stateless and Open WebUI owns
conversation state, so a condensation/rewrite step needs a deliberate home. This
is a design decision, not a tuning gap.

### 2.6 R5 is untested in the visual arm

Every measurement ran `RAG_MAX_PAGES=25`. That cap applies **only** to
`_render_pages` (the visual arm); the text arm always extracted in full via
docling, so the prose numbers are sound. But page images for pages 26+ of the 10
long documents were never built, so the visual arm has never been exercised at
production scale, cost, or latency. The shipped default is 500.

### 2.7 Tables are docling's justification and are unmeasured

docling was adopted for layout and table structure. There is **not one query in
the set targeting a real CIP requirement, applicability, or evidence table**.
The single query that implicitly needs one (`prose-cip-07`) is the one that
fails.

## 3. What IS established (do not re-litigate)

- **`text_gate`'s design is sound**, and this result is weighting-independent:
  on the docling index τ=0.00 (never fires) reproduces B1 exactly (diagram r@1
  0.000, MRR 0.500), and τ=1.01 (always fires) costs prose r@1 0.875 → 0.688.
  Both the boost and its conditionality are load-bearing.
- **τ=0.72 is the true knee of the sweep as measured** — 0.75 is strictly
  dominated (same diagram recall, −0.062 prose r@1).
- **docling is the better text arm** (prose r@1 0.812 → 0.875 on the 2.124
  build) and is now pinned host-side (`>=2.99.0`) and container-side
  (`==2.99.0`), with the transformers ceiling documented.
- **Root cause of the τ failure is separability, not calibration**: PyMuPDF gave
  a clean 0.098 gap between diagram and prose cosine populations; docling
  collapses it to a 0.072 overlap, making 3 errors of 37 the information floor.
- The single-worker MLX executor, launchd supervision, and the S0 model
  selection are independent of all of the above and stand.

## 4. What is NOT established

Answer quality · multi-document retrieval (R3) · table retrieval · long
documents in the visual arm (R5) · conversational use (R4).

**τ=0.72 is not evidence that the system is fit for compliance Q&A.** It is
evidence about one fusion knob under one unrepresentative query distribution.

## 5. What needs to be done

Ordered so that each step's output is the next step's input. **τ is re-derived
last** — deriving it first is the mistake that produced this task.

### W1 — Rebuild the evaluation corpus and query set around the real task
- Drop or heavily de-weight the 21 synthetic diagram queries; keep a small
  figure-reading subset only as a regression guard for the visual arm.
- Author queries against the **real** corpus, covering:
  - a CIP requirement table lookup (CIP-002 Attachment 1, CIP-007 R2 tables),
  - an applicability / evidence table,
  - an operator-policy procedural question,
  - **R3 pairs**: "does `<our policy>` satisfy `<standard requirement>`",
  - at least one target beyond page 25 of a long standard.
- Record, per query, **every** document a correct answer must cite — not one
  `target_file`.

### W2 — Replace the metric with one that can express R3
- Multi-target scoring: precision/recall over the **set** of required documents
  within top-k, not rank of a single file.
- Report source diversity (distinct documents in top-k) as a first-class number.
- Keep single-target recall@1/@5 as a secondary series for continuity with the
  existing sweeps.
- **Per-query rows must stay visible in the report**, since the aggregate is
  what hid `prose-cip-07`'s decay across three builds.

### W3 — Re-run the provisional rejections against W1/W2
- `RAG_CHUNK_STRATEGY=structured` vs `fixed`.
- `VL_FUSION=unified` (text depth 3) vs `text_gate`.
- Both currently ship as A/B switches with their losing numbers recorded at the
  definition site; those comments must be corrected or confirmed by this run.

### W4 — Fix `prose-cip-07` specifically, and understand why
- Determine whether the failure is chunk-boundary (the criteria table split
  across fixed 1000-char windows) or embedding (query/passage mismatch on
  tabular content).
- This is the acceptance case for the whole task: a table-answered question
  about a named standard must return that standard.

### W5 — Decide and implement R4 (conversations)
- Choose where turn-aware query rewriting lives without violating Rule 4
  (Pipeline stateless, OWUI owns conversation state).
- Add follow-up query chains to the eval; measure retrieval quality on turn 2+
  where the query is elliptical.

### W6 — Exercise R5 at production scale
- Ingest the real corpus with the default `RAG_MAX_PAGES=500`.
- Measure ingest wall time, page-image count, storage, and query latency; decide
  whether the visual arm needs a page budget or a figure-page filter
  (`_figure_pages` already exists and may make the cap unnecessary).

### W7 — Re-derive τ last
- Sweep on the corrected query set and metric.
- Update `tests/fixtures/rag_eval_corpus/retrieval_eval_baseline.json` (sweep,
  fingerprint) so the existing staleness guards continue to hold.

## 6. Acceptance criteria

1. The eval's query distribution reflects the real corpus, and every query
   declares the full set of documents a correct answer requires.
2. An R3 question scores on retrieving **both** the standard and the policy;
   returning only one is a miss.
3. `prose-cip-07` returns `cip-002-5.1a.pdf` at rank 1, with the cause
   understood and recorded.
4. The structure-chunking and `unified` verdicts are re-run and either confirmed
   or reversed on the corrected metric, with the code comments updated.
5. A follow-up turn retrieves correctly against an elliptical query, or R4 is
   explicitly deferred with a documented design decision.
6. The real corpus ingests uncapped, with cost and latency measured.
7. τ is re-derived on the corrected set and `tests/fixtures/rag_eval_corpus/retrieval_eval_baseline.json` is
   updated; the seven staleness guards still pass.
8. Per-query results are published, not only aggregates.

## 7. Notes for whoever picks this up

- **The eval cannot run in CI** — it needs the MLX VL server on Apple Silicon,
  ~21 min of ingest, and the operator's private compliance PDFs. Those PDFs are
  marked *PRIVATE — FOR INTERNAL USE ONLY* and are **not committed**; keep it
  that way.
- The committed unit tests catch **invalidation** (a dependency, model, or
  strategy change), not **regression**. `prose-cip-07` decaying across three
  builds would pass every one of them. Only the eval sees that.
- Do not bump `docling` past 2.99.0 without re-deciding the `transformers`
  pin — `docling>=2.100` pulls `docling-core[chunking]`, which caps
  `transformers<5.9.0` against the `>=5.16.1` the qwen3_vl mapping needs. A bare
  `pip install docling` resolves this by silently downgrading transformers
  underneath the running VL server.
- Aggregate scores hid every problem in this document. Read per-query rows.
