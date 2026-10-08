# EmbeddingGemma 2 cutover — per-consumer verdicts and what shipped

TASK_EG2_CUTOVER_V1, 2026-10-08. Run stamps are directories under `reports/embedding_consumers/`.
Every comparison is paired (same probes, both arms) unless stated.

## Switched to EG2 (live)

| consumer | evidence | shipped |
|---|---|---|
| graph memory (`:8920`) | `memory_recall` r@4 0.975 vs 0.925 (`20261007T224205Z`); floor `20261007T220949Z` | SEARCH 768d via `EmbeddingClient`, `MEMORY_RECALL_FLOOR` 0.60, cosine; store re-embedded (69 memories, 225 entities), live recall@4 0.975 through `_remember`/`_recall` |
| Open WebUI RAG | `owui_attachment_rag` hybrid+bge r@3 0.808 vs 0.638 (`20261008T021720Z`) | `:8946/v1`, contract SEARCH prefixes; 883/888 collections re-embedded (5 unreachable leftovers) |
| RAG MCP + compliance retrieval | `rag_first_stage` (`20261008T015224Z`), `compliance_retrieval` parity 0.810 vs 0.816 (`20261008T022653Z`) | `VL_RETRIEVAL_URL` `:8946/vl`, 768d; `VL_TEXT_GATE` 0.88 from a full τ sweep on the production eval corpus (32 docs incl. 9 operator procedures, 42 queries): diagram and prose r@1 1.000 (0.72 on EG2: diagram 0.333). Qwen3-VL reranker on :8942 retained |

## Kept on the incumbent (measured worse on EG2)

| consumer | evidence |
|---|---|
| auto-router | LLM 66/73 vs EG2 anchor classifier 58/73, exact McNemar p=0.039 (`20261007T220949Z`) |
| `classify_vulnerability` | CIRCL RoBERTa macro-F1 0.504 vs 0.367 on post-cutoff CVEs, p=0.0009 (`20261008T023549Z`); both arms weak |

## Bully hunt-memory projection — corrected, switch pending

The earlier "Qwen3 wins, p=0.039" (`20261008T025427Z`) was an artifact: the discovery engine saw
each probe's truth labels (ATT&CK technique on 988/988 probes, scenario family on 672) — fixed in
`c082c808`. The corpus also carried no field values and only 32 events per dataset — fixed in
`0594b5e4` (SPECIMEN_CORPUS_V3, `bully.behavior_values`).

| corpus (blind, 988 probes, related references) | Qwen3 | EG2 + sentence-similarity prefix | TF-IDF |
|---|---|---|---|
| V2 (field names only) | 43 | 66 | 99 |
| V3 (behavior values from the source datasets) | 139 | 154 | 148 |
| V3 excluding evidence twins | 111 | 132 | 123 |

`bully_projection` on V3 (`20261008T164221Z`): 53 vs 68 discordant, p=0.20 — EG2 is not worse.
Masking lab identity changes nothing (p≥0.29). Open: cross-source discovery is 0–1/988 in every
arm (engine weighting), see KNOWN_LIMITATIONS BULLY-DISCOVERY-TRUTH-LEAK-001.

## Findings outside the embedder decision

* `VL_TEXT_GATE` under EG2: the visual boost is load-bearing (τ=0 → diagram r@1 0.000) but the
  gate's conditionality is not shown to be: every τ ≥ 0.88, including always-blend, scores the
  same on 42 queries. Simplifying fusion is C7's decision, not taken here.
* Open WebUI's 2 GiB container cannot hold a second chromadb client (exit 137 restarted it);
  `scripts/owui_reembed.py verify` reads Chroma's sqlite catalog instead.
* The browser MCP described itself as Playwright after the Obscura swap; fixed `e812e263`.
