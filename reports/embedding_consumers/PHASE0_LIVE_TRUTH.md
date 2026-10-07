# Phase 0 live truth — 2026-10-07, HEAD ceb4b829, arm64

Payloads: MANIFEST 21/21 OK; `phase1_apply.py --check` 29 APPLY + 4 DELETE, 0 FAIL.

## a. :8917 identity
`/health` → `{"model":".../Qwen3-Embedding-0.6B-mxfp8","loaded":true,"backend":"mlx"}`. Launchd `com.portal5.embedding` (PID 3883) runs `scripts/embedding-server-mlx.py`. Retired Harrier server is NOT serving, so the Phase 1.2 Harrier stop is a no-op. RSS of the python worker ≈ 106 MB (weights are in MLX unified memory).

## b. :8925
`/health` → `{"model":"mlx-community/Qwen3-Reranker-0.6B-mxfp8","loaded":false}`; container logs show only health probes (no rerank call ever). Container RSS 21 MiB. Confirms R-8925.

## c. Open WebUI (running image, word-exact grep)
UNREAD: MEMORY_EMBEDDING_MODEL, ENABLE_MEMORY_FEATURE, ENABLE_RAG_WEB_SEARCH, RAG_WEB_SEARCH_ENGINE, RAG_WEB_SEARCH_RESULT_COUNT, RAG_WEB_SEARCH_CONCURRENT_REQUESTS, ENABLE_API_KEY, ENABLE_WORKSPACE, USER_PERMISSIONS_CHAT_DELETION, USER_PERMISSIONS_CHAT_EDITING.
Successors read by the image: ENABLE_API_KEYS (rename, behaviour-preserving), ENABLE_MEMORIES, ENABLE_WEB_SEARCH / WEB_SEARCH_ENGINE / WEB_SEARCH_RESULT_COUNT / WEB_SEARCH_CONCURRENT_REQUESTS (NOT renamed: would enable web search; effective ENABLE_WEB_SEARCH is currently False).
Audio STT config: `ENGINE: ""`, `MODEL: ""`, `WHISPER_MODEL: "base"`, `SUPPORTED_CONTENT_TYPES: []` → empty engine is local faster-whisper; STT is NOT disabled (F-STT-CLAIM confirmed).
Publish side effect (1 s wav upload): without `process=false` → `data.status=pending`, `data.content` 24022 chars (processed); with `?process=false` → no status, content length 0. F-PUBLISH confirmed.
Retrieval config: BYPASS_EMBEDDING_AND_RETRIEVAL=False, RAG_RERANKING_MODEL=BAAI/bge-reranker-v2-m3, hybrid search True.

## d. Router
Layer counts (30d): fallback_auto 31, keywords 2, llm 8. `ollama ps`: router tag `...OBLITERATED-GGUF:Q4_K_M-ctx2k` resident, 5.4 GB, ctx 2048, runner llamacpp, UNTIL Forever. OWUI `TASK_MODEL_EXTERNAL=task-router`. (Prometheus has no `task-router` series under the queried metric name; binding itself is confirmed.)

## e. Parallel stores
OWUI memories 26; OWUI knowledge collections 2; memory MCP stored 69, graph entities 225 / relations 174, intact. Bully `hunt_memory` embedding_version breakdown: not queried in Phase 0 (revisit in the bully_projection probe).

## f. Injection
`auto_context_inject_total` 30d: memory hit ≈109, memory error ≈30 (rag: none). `toolpreselect_calls_total`: no samples. AUTO_* flags are not set in `.env` (code defaults apply; AUTO_RAG_ENABLED default false per task).

## g. RSS
`vl-retrieval-server` 163 MB, `embedding-server-mlx` 106 MB (host RSS excludes MLX unified-memory weights); `portal5-open-webui` 209 MiB, `portal5-mcp-reranker` 21 MiB (Docker).

## h. :8942
`/ready` → `ready: true`, `mlx-community/Qwen3-VL-Embedding-2B-mxfp8`, dim 2048; launchd `com.portal5.vl-retrieval` running.

## Other
Ollama has `embeddinggemma-2:740m-mxfp8` (1.4 GB) installed.
