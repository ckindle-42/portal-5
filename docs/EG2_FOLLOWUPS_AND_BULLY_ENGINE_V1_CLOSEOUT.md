# TASK_EG2_FOLLOWUPS_AND_BULLY_ENGINE_V1 — closeout

2026-10-08. One line per item, evidence path or run stamp per line. Commits: `1ee68f4b` (B1.3),
`5da11b00` (B1.4), `fc9b8bfa` (B2), `bc280cf6` (R2), `b7911c3b` + `02cd2b6a` (H1), `e0f5fe07` (R1).

## B1 — Bully engine cross-source discovery

- **B1.1 instrumentation** — DONE: `reports/bully_b1/20261008T195439Z/b1_instrumentation.json` —
  154/988 probes choose a truth-related reference, 276 retrieve one and outrank it (best-truth
  rank 1–6 for 237), 558 retrieve none; cross-class truth candidates in the candidate set have
  semantic distance ≈ the chosen same-source records (0.069 vs 0.061) while action-sequence
  behavior differs (0.849 vs 0.249) — the values channel is what carries them.
- **B1.2 weight variants, paired** — DONE: `reports/bully_b1/20261008T195439Z/b1_summary.json`;
  harness `scripts/bully_b1_engine_variants.py` (base arm reproduces the cutover's 154 exactly).
- **B1.3 adoption** — DONE (`1ee68f4b`): cousin-v2 = weights {behavior 0.40, semantic 0.40,
  telemetry 0.10, context 0.10, attack 0.15} + behavior channel on `artifacts.behavior_values`
  with an action-sequence fallback. Paired vs v1 on the same 988 probes and projection: related
  154 → 241 (p<1e-4), cross-source 1 → 16 (p=6e-5); twins reported separately (97); hand-checked
  cross-source sample genuine. Raw down-weight rejected (mass 0.40 < MIN_CONFIDENCE — everything
  ANOMALOUS). Five of the six `TRUTH_LEAK_XFAIL` tests un-marked; the sixth resolved in B1.4.
- **B1.4 thresholds** — DONE (`5da11b00`, its own commit/numbers):
  `reports/bully_b1/20261008T195439Z/THRESHOLDS_B1_4.md`. Reference constants re-measured on
  EG2+V3 (self 0 / near 0.1336 / far 0.1630); clamp KEPT (never binds for the primary space —
  EG2 sits above the retired harrier constants everywhere). `same_max_distance` 0.05 → 0.063 on
  the measured identity-composite distribution (median 0.0387, max 0.0621; frozen 0.05 failed
  2/100 self-pairs); ranking untouched (241 before/after), 4 chosen pairs move DISCOVERY →
  REGRESSION. `THRESHOLDS_VERSION` → v2; all six former xfails now pass unmarked.
- **Still open (recorded, not this task):** 558/988 probes retrieve no truth-related candidate —
  retrieval-axis coverage is the next binding constraint (in KNOWN_LIMITATIONS).

## B2 — leak-invalidated run reports

- **DONE** (`fc9b8bfa`): the sweep over `docs/BULLY_*_RUN_*.md`/`.json` and the design docs found
  exactly two reporting discovery-lane numbers — `BULLY_BUILD_PROGRESS.md` (SA2 section) and
  `BULLY_BASELINE_CALIBRATION_V3.md` (its successor pointer). Both carry superseded notes citing
  the blind V3 re-runs (`20261008T164221Z`, `20261008T195439Z`) and
  BULLY-DISCOVERY-TRUTH-LEAK-001; historical numbers untouched. No other run doc exercised the
  discovery lane (forge/unknown-cousin lanes plant relationships and are not leak-affected).

## B3 — Bully production projection on EG2

- **DONE**: production `hunt_state.db` `index_outbox` is empty (no backlog) and the
  `hunt_memory` LanceDB projection has no tables — nothing to re-seed, matching the cutover
  record. The production path was verified live against `:8946/embed` on a throwaway store:
  `index_emissions` → `process_outbox` {leased 1, completed 1, failed 0} with the identity check
  passing, 768d row projected under `hunt-memory-v1` /
  `google/embeddinggemma-2:768d:sentence-similarity`, and the persisted `RecallReceipt` carrying
  the same `embedding_version` with `source_health {"embed": "ok"}`.

## R1 — RAG fusion (e0f5fe07; `reports/embedding_consumers/20261008T220000Z/`)

- **Query set extended** — DONE: 42 → 52 public queries; 10 operator-document questions grounded in
  the production corpus's nine operator procedures, with justified `also_accept` standard↔procedure
  pairs (`tests/fixtures/rag_eval_corpus/queries.yaml`); an 11th question stays in the
  operator-local query set beside the production corpus — operator-internal down to its target
  file name, so HK keeps it out of the public tree.
- **text_gate vs always-blend** — **REJECTED always-blend (evidence: ties)**: on the extended
  set every τ ≥ 0.88 including 1.01 scores identically (all r@1 0.962; 0.86 loses 1 prose hit),
  so 0.88 stays and the gate keeps its guard role; the tie gives simplification no measured
  gain and a switch costs a pipeline rebuild.
- **Drop the :8942 reranker from RAG?** — **REJECTED (evidence: not shown; incumbent stays)**:
  on 52 public queries embed_sim 0.846 all r@1 vs reranked 0.962 (prose 0.769 vs 0.923; paired
  7 vs 1 flips, exact McNemar p=0.070 — `text_gate_088_rows.json`). Corrected 2026-10-08: first
  recorded as "53 queries, 15 vs 3, p=0.008", which paired against rows scored at τ 0.72. The cutover's
  first-stage finding did not survive the extended set. Compliance's operator lane keeps its reranker regardless.
- **OWUI hybrid weight** — DONE: dense-only 0.8085; hybrid identical at every bm25 weight
  0.0–0.4, harmful only at 0.5 (0.6383). `RAG_HYBRID_BM25_WEIGHT` 0.5 → 0.2 applied live via
  `POST /api/v1/retrieval/config/update`; hybrid stays enabled. Persisted for fresh installs in
  `deploy/portal-5/docker-compose.yml` (the live value lived only in the OWUI DB).

## R2 — compliance retrieval on the operator corpora

- **q01_U / q03_U / q07_C root cause** — DONE (`bc280cf6`): q01_U/q03_U are stale vocabulary
  (fdd56bf8 projects council ESCALATE/INSUFFICIENT → UNRESOLVED — the same loud-not-silent
  semantics the tests check); q07_C is the reading-pass contract (propose re-judges through
  `assess_part`, whose documentary coverage needs a per-duty reading JSON the old scripted seat
  never provided) — fixed with a `_reading_seat`. 22/22 pass; both failures reproduce on the
  pre-cutover commit (offline policy-graph drift, not retrieval).
- **Corpus re-projection** — NOT ADDRESSED here by design: the operator/NERC corpora live in the
  Qwen3-VL 2048d space and their EG2 re-projection is owned by TASK_COMPLIANCE_DATA_TRUTH_V1
  Amendment 4 (A4.3 step 6), per the task's own correction.

## H1 — harness and housekeeping

- **Probes' retired incumbent arm** — DONE (`02cd2b6a`): `_common.HISTORICAL_ARMS` freezes the
  :8917 arm's committed scorecard blocks with provenance; `legacy_embed` deleted;
  `owui_attachment_rag` and `bully_projection` restructured to the fixed incumbent; lexical
  `incumbent_rank` baselines kept.
- **Open WebUI dead collections** — DONE (live action): the five 1024d collections (`test`,
  `test_chat_rag`, `compliance_test`, two orphaned `file-*`) were deleted through the in-container
  chroma client after a `chroma.sqlite3` backup; `scripts/owui_reembed.py verify` now reports 883
  collections, all 768d, exit 0; OWUI healthy throughout. No REST endpoint manages raw
  collections, so the deletion used the container directly — recorded here as the audit trail.
- **context_inject recall contract** — DONE (`b7911c3b`): dispatches `top_k` (schema-verified
  against the live tool), contract test added, SEAM-V1-AUTORAG-001 class closed.
- **Auto-router** — NOT ADDRESSED by design: stays on the LLM (p=0.039); an EG2 pre-filter is a
  separate measured proposal, not this task's swap.
- **TASK_POST_EG2_FOLLOWUPS_V1** — still open elsewhere; not duplicated here.
