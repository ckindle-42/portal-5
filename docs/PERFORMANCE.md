## P7-PERF Pipeline Optimizations

<!-- WIKI:GENERATED unit=unit-performance-p7-perf-pipeline-optimizations -->
`P7-PERF` is the comment marker for a batch of pipeline routing optimizations measured against `bench_tps.py` output. Grepping for `P7-PERF` surfaces the affected paths rather than any single module:

- `cluster_backends.py` — the TTL-cached backend candidate list (`get_backend_candidates`), cache invalidation on health changes, and the cache-first fast path with unknown-id clamping.
- `router/routing.py` — reuse of the shared `httpx` client by the LLM router and the pre-compiled `_KEYWORD_CACHE` in the keyword scorer.
- `tests/benchmarks/bench/measure.py` — the module-level reusable bench `httpx.Client` (`_get_bench_client`).

The common theme is turning per-request work into import-time or first-use work: candidate lists, keyword dicts, and HTTP connection pools are each built once and reused across the steady-state request path.

## Why

The marker exists because these optimizations were driven by benchmark evidence rather than speculation: `bench_tps.py` highlighted routing overhead that sat between the raw Ollama endpoint and the pipeline endpoint, and each `P7-PERF` comment anchors a specific fix back to that measurement. Keeping the marker in the code makes the relationship between each optimization and its measured motivation auditable at the exact line where the shortcut lives, which matters because routing shortcuts are exactly the kind of change later readers hesitate to touch without knowing why it is there.
<!-- /WIKI:GENERATED -->

---

### LLM Router Warmup at Startup

<!-- WIKI:GENERATED unit=unit-performance-llm-router-warmup-at-startup -->
`_warmup_llm_router()` in `portal/platform/inference/router/lifespan.py` fires at pipeline startup (as a background task from `_run_startup_warmups`) to pre-load the LLM intent-classifier model into Ollama before the first `auto`-routed request arrives. It posts a minimal `num_predict: 1` generate call to `${LLM_ROUTER_OLLAMA_URL}/api/generate`.

The load-bearing option is `keep_alive: -1` sent as a JSON integer. Ollama 0.30.8+ rejects the string form `"-1"`, so the payload pins the classifier model in memory indefinitely rather than letting a larger inference model evict it. `options.num_ctx` is set to `2048` to match the routing call in `_route_with_llm`, preventing the warmup from reserving tens of GiB via an over-wide context window. The warmup is skipped entirely when `LLM_ROUTER_ENABLED=false` — those deployments fall back to `_detect_workspace` keyword scoring and need no pin.

## Why

Every request that routes through the `auto` workspace first asks the classifier model for a routing decision, so a cold classifier adds a full model load to the first user request even when the inference model is already warm. Warming up alone is not enough — without a persistent pin the classifier is evicted the moment a large inference model loads, returning the deployment to a cold load on the next request. The integer keep-alive, the matched context window, and the feature-flag gate are the three knobs that make residency durable instead of a one-shot preload.
<!-- /WIKI:GENERATED -->

---

### Shared HTTP Client

<!-- WIKI:GENERATED unit=unit-performance-shared-http-client -->
The pipeline creates one `httpx.AsyncClient` at startup in `portal/platform/inference/router/lifespan.py`, configured with `httpx.Timeout(600.0, connect=5.0)` and `httpx.Limits(max_keepalive_connections=20, max_connections=100)`. That client is then propagated to the modules that need it — routing (`_route_with_llm`), streaming, and the council — via direct assignment of `_http_client` at lifespan setup, so every backend request shares the same connection pool.

The LLM intent router uses this shared client rather than creating per-request clients, with the shorter router timeout enforced by `asyncio.wait_for` wrapping the call instead of a second client built for the router's millisecond budget. This keeps one pool for all backend traffic while still letting the router fail fast.

## Why

Connection pooling matters because the pipeline talks to local Ollama backends on the same host, and opening a fresh connection per request would trade away keepalive reuse on every inference call. The design also reconciles two conflicting timeout needs without duplicating the client: inference wants a long body timeout for cold model loads, while the LLM router needs to fail within its configured millisecond budget. Sharing the pool and layering the fast-fail above it with a wait-for is what makes both requirements hold at once.
<!-- /WIKI:GENERATED -->

---

### Keyword Cache

<!-- WIKI:GENERATED unit=unit-performance-keyword-cache -->
The Layer-2 keyword scorer (`_detect_workspace` in `portal/platform/inference/router/routing.py`) ranks the last user message against per-workspace keyword dictionaries. At module import time the router pre-compiles every workspace's keyword dict to lowercase into the module-level `_KEYWORD_CACHE`, a `{workspace_id: {keyword: weight}}` map.

At request time the scorer lowercases the user message exactly once, then for each cached workspace sums the weights of keywords found in that text and keeps the workspaces whose score clears their configured `threshold`. The cache eliminates the two per-request costs a naive implementation would pay: a `.lower()` per keyword (tens of keyword strings per workspace) and a rebuild of each keyword dict on every request.

## Why

The keyword scorer runs on the fallback path of every request the LLM router cannot confidently classify, so its steady-state cost is paid whether or not routing succeeds. Pre-lowering the keywords at import time moves an O(keywords) transformation off the hot path, leaving each request with one lowercase pass over the user text and a bounded set of substring checks. The invariant this cache protects is that keyword fallback stays cheap enough to run on every uncertain request without becoming a measurable latency item.
<!-- /WIKI:GENERATED -->

---

### Backend Candidate Cache

<!-- WIKI:GENERATED unit=unit-performance-backend-candidate-cache -->
`BackendRegistry.get_backend_candidates()` caches its per-workspace result in `_candidate_cache` with a 5-second TTL (`_candidate_cache_ttl = 5.0`). A cache hit returns a fresh list copy without re-scanning the healthy backend list, re-running the group-priority sort, or calling `random.shuffle()` on the fallback tiers.

The cache is invalidated eagerly, not just TTL-expired: `_refresh_healthy_cache()` calls `_invalidate_candidate_cache()` after every `health_check_all()` cycle, so a backend that just went unhealthy drops out of routing within one health cycle (30s default) instead of lingering until its TTL entry ages out. Unknown workspace ids are clamped to `_unknown` so the cache dict cannot grow unbounded.

## Why

The candidate-selection cost matters because it runs on the hot path of every request that names a workspace, while backend health only changes on the 30-second health cycle. Without the cache each request would rebuild the ordered candidate list from the full backend table, paying a list comprehension plus a shuffle per group even though nothing changed. The cache converts that steady-state cost into one dict get and a list copy, and the health-cycle invalidation guarantees freshness on the timescale that actually matters: the moment a backend becomes unhealthy.
<!-- /WIKI:GENERATED -->

---

### Benchmark Client Reuse

<!-- WIKI:GENERATED unit=unit-performance-benchmark-client-reuse -->
The TPS benchmark reuses a single `httpx.Client` across all runs. `_get_bench_client()` in `tests/benchmarks/bench/measure.py` lazily creates a module-level `_bench_client` on first use and returns it for every subsequent `bench_tps()` call, with the pool configured as `httpx.Limits(max_keepalive_connections=10, max_connections=20)`.

`bench_tps.py` itself is now a thin entry-point shim that re-exports `bench_tps` from the `tests.benchmarks.bench` package, so the reuse lives in `measure.py` while the operator-facing command line is unchanged. The pipeline warmup step (`_warmup_pipeline_model`) deliberately opens a throwaway client because it runs before timing starts.

## Why

Reusing the client matters because the benchmark measures pipeline latency, and a fresh `httpx.Client` per run would fold TCP connect and TLS handshake cost into every measured request. Connection reuse keeps the measured number close to true inference throughput, so the comparison between direct and pipeline modes stays a comparison of the serving paths rather than of client setup overhead.
<!-- /WIKI:GENERATED -->

---

## Benchmarking

<!-- WIKI:GENERATED unit=unit-performance-benchmarking -->
TPS benchmarking is driven by `tests/benchmarks/bench_tps.py`, a shim that forwards to the `tests.benchmarks.bench` package. A typical pipeline invocation is:

```
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto --runs 3
```

`--mode` accepts `direct` (raw Ollama), `pipeline` (workspaces through the portal pipeline), `personas` (persona routing), or `all`. `--workspace` filters pipeline runs to an exact workspace id and `--runs` sets the per-model trial count. Results are written to a timestamped JSON under `tests/benchmarks/results/` (`RESULTS_DIR`), and the CLI prints a summary ranking runs by `avg_tps`.

Running the same model through `direct` and `pipeline` modes is the intended way to measure the portal layer's per-request overhead, because both modes use the same shared bench client and warmup path, so the delta isolates routing, auth, and proxy cost from inference.

## Why

A benchmark is only useful if its numbers are comparable across runs. The harness warms each model to a loaded state before timing, reuses one HTTP client so connection setup is not measured, and unloads or drains models between tests so one run cannot contaminate the next. The direct-versus-pipeline comparison exists specifically to keep the portal's routing overhead visible instead of burying it inside a single end-to-end number.
<!-- /WIKI:GENERATED -->

---
