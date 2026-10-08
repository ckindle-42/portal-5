# R1 — RAG fusion decisions on the extended production query set

TASK_EG2_FOLLOWUPS_AND_BULLY_ENGINE_V1 R1, 2026-10-08. The 42-query set was at ceiling for the
text-gate decision; it is extended to **52 public queries** with 10 operator-document questions (an 11th, operator-internal down to its target file name, lives in the operator-local query set beside the production corpus and is not part of the committed evidence)
(`tests/fixtures/rag_eval_corpus/queries.yaml`, section "operator documents · standard-and-
procedure pairs") grounded in the production corpus's 9 operator procedures, several with
`also_accept` links where the governing NERC standard and the implementing procedure both state
the answer (each justified inline). Corpus: the cutover's rag_prod set (32 docs incl. the
operator PDFs), cached Lance + arms from the EG2 cutover.

## τ sweep, text_gate on 52 public queries (`tau_sweep_extended.json`)

| τ | diagram r@1 | prose r@1 | all r@1 |
|---|---|---|---|
| 0.72 | 0.333 | 0.815 | 0.635 |
| 0.80 | 0.857 | 0.885 | 0.885 |
| 0.86 | 1.000 | 0.885 | 0.942 |
| **0.88** | **1.000** | **0.923** | **0.962** |
| 0.90–1.01 (incl. always-blend) | 1.000 | 0.923 | 0.962 |

**Decision: KEEP VL_TEXT_GATE 0.88. REJECT always-blend.** Every τ ≥ 0.88 — including
always-blend (1.01) — scores identically on the extended set, so the gate's conditionality is
still not shown to be load-bearing; but the tie means simplification buys nothing measured,
while the gate remains the conservative guard for a confident-but-wrong text arm on unseen
queries, and switching costs a pipeline rebuild. 0.88 is confirmed as the knee (0.86 loses 4
prose hits).

## embed_sim vs the reranked arm on 52 public queries (`embed_sim_extended.json`)

| arm | diagram r@1 | prose r@1 | prose r@5 | all r@1 |
|---|---|---|---|---|
| text_gate 0.88 (reranker live) | 1.000 | 0.923 | 1.000 | 0.962 |
| embed_sim (no reranker) | 0.952 | 0.769 | 0.962 | 0.846 |

18 queries flip hit@1 between the arms, 15 in favor of the reranked arm, 3 in favor of
embed_sim — exact McNemar p = 0.008. **The cutover's first-stage finding does not hold on the
extended set: REJECT dropping the :8942 reranker from RAG.** (Compliance's operator lane keeps
its reranker regardless — dense 0.583 vs reranked 0.717 there.)

## OWUI hybrid_bm25_weight sweep (`owui_hybrid_sweep.json`)

Dense-only recall@3 = 0.8085 on the wiki fixture; hybrid is **identical at every bm25 weight
0.0–0.4** (the lexical arm never displaces the dense top-3 units) and harmful only at 0.5
(0.6383, the cutover's measured regression). **Applied `HYBRID_BM25_WEIGHT = 0.2` live** via
`POST /api/v1/retrieval/config/update` (was 0.5): removes the regression, keeps the lexical arm
for exact-token queries, reversible by the same API. Hybrid stays enabled.
