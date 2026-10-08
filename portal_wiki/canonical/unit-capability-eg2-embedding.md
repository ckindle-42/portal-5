---
id: unit-capability-eg2-embedding
kind: mixed
title: "EmbeddingGemma 2 platform embedder (:8946)"
sources:
- type: code
  path: scripts/eg2-embedding-server.py
- type: code
  path: portal/platform/embedding/__init__.py
- type: code
  path: portal/platform/embedding/contract.py
- type: code
  path: portal/platform/embedding/client.py
- type: code
  path: portal/platform/embedding/classifier.py
- type: code
  path: scripts/eg2-venv-setup.sh
- type: code
  path: scripts/native-mcp-service.sh
claims: []
confidence: high
tags:
- capability
- embedding
- host-native
created_at: 1791388800
updated_at: 1791388800
---

# EmbeddingGemma 2 platform embedder (:8946)

## What

`google/embeddinggemma-2` served host-native on port 8946 by `scripts/eg2-embedding-server.py`
(sentence-transformers, bf16 on MPS) in its own venv `~/.portal5/eg2-venv`, supervised by launchd
(`com.portal5.eg2-embedding` via `scripts/native-mcp-service.sh eg2-embedding`). One 768-d space for
text, code, images, audio and video, with Matryoshka truncation (512/256/128) and task-steered prefixes.

Memory: `:8946` calls `torch.mps.empty_cache()` after every encode. Before `1f82362f` it (and the since-retired `:8917` MLX embedder) grew to 55+ GB and caused watchdog resets. The :8917 service was retired in TASK_EG2_CUTOVER_V1 once its last consumer, Bully, measured not-worse on EG2.

Surfaces: `/health` (never loads the model), `/ready` (loads, probes NaN-freedom, prefix asymmetry and
MRL renormalisation, returns the served identity), `/embed` and `/embed_items` (Portal contract; prefixes
applied server-side from `portal/platform/embedding/contract.py`), `/v1/embeddings` (OpenAI-compatible, raw,
rejects a foreign `model`), `/v1/rerank` and `/vl/*` (forwarded to the Qwen3-VL server on :8942, which stays
the reranker). Readiness check `HN` in `scripts/validation/rag_runtime.py` asserts `/ready` when the service is
installed.

## Consumers (TASK_EG2_CUTOVER_V1, 2026-10-08)

| consumer | path | task / role | dim | shipped thresholds |
|---|---|---|---|---|
| graph memory (`:8920`) | `EmbeddingClient` `/embed` | SEARCH; memories + entity names = document, recall query = query | 768 | `MEMORY_RECALL_FLOOR` 0.60 cosine |
| Open WebUI RAG | `/v1/embeddings` (raw) | SEARCH prefixes via `RAG_EMBEDDING_{QUERY,CONTENT}_PREFIX` | 768 | Open WebUI's own (top_k 3, bge rerank) |
| RAG MCP + compliance retrieval | `/vl/*` | SEARCH; `is_query` items = query | 768 (`EG2_VL_DIM`) | `VL_TEXT_GATE` 0.88 |
| Bully hunt-memory projection | `Organ` → `/embed` | SENTENCE_SIMILARITY (symmetric) | 768 | engine's own (`cousin_engine.DEFAULT_THRESHOLDS`) |

Kept off EG2 on evidence: the auto-router (LLM beats the anchor classifier, p=0.039) and
`classify_vulnerability` (CIRCL RoBERTa, p=0.0009). The Qwen3-VL reranker on :8942 stays
behind `/vl/rerank` and `/v1/rerank`.

## Why / gotchas

* The client library `portal/platform/embedding/` is stdlib + httpx only (Rule 8: nothing under
  `portal/platform/` imports numpy/torch/transformers).
* Runtime dependencies the model card does not list: `torchvision` (processor import), `librosa` + `soundfile`
  (audio), `torchcodec` + `av` (video). `scripts/eg2-venv-setup.sh` installs them explicitly; the
  sentence-transformers `[audio]` extra is avoided because it pulls `kenlm`, which fails to build on cpython-3.13.
* The venv is on uv cpython-3.12.12. macOS TCC grants `/Volumes/data01` access per interpreter binary; the first
  launch of this fresh interpreter was denied (`kTCCServiceSystemPolicyAllFiles authValue=0`) and `/ready` hung in
  `open()` on the model cache until the operator approved the binary on 2026-10-07. Changing the Python version or
  uv patch level creates a new binary needing approval again. The model cache is the standard
  `~/.cache/huggingface` -> `/Volumes/data01/hf-cache`.
* `*_path` inputs are only honoured under `EG2_MEDIA_ROOTS` (default AI_Output, data01, temp dir); otherwise send `*_b64`.
* bf16 or fp32 only; fp16 yields NaN.
* Ollama also serves the model (`embeddinggemma-2:740m-mxfp8`); it applies no task prefixes and rejects video.
  Measured parity and throughput are in `reports/embedding_consumers/RUNTIME.md`. Runtime choice between the
  two is a Phase-4 operator gate of `coding_task/TASK_EMBEDDINGGEMMA2_PLATFORM_V1.md`.
