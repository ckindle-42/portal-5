# Performance Optimizations

## P7-PERF Pipeline Optimizations

Optimizations targeting routing overhead identified by `bench_tps.py`. Look for `P7-PERF` comments in code to find these paths.

### Shared HTTP Client
All backend requests use a single `httpx.AsyncClient` with connection pooling (20 keepalive, 100 max connections). The LLM router also uses this shared client instead of creating per-request clients.

### Keyword Cache
Workspace keyword dictionaries are pre-compiled to lowercase at module load (`_KEYWORD_CACHE`). Eliminates repeated `.lower()` calls and dict rebuilding on every request.

### Backend Candidate Cache
`get_backend_candidates()` results are cached with a 5-second TTL. Cache is invalidated after health checks. Avoids list comprehension and `random.shuffle()` on every request.

### Benchmark Client Reuse
`bench_tps.py` reuses a single httpx client across all benchmark runs for accurate pipeline latency measurement.

---

## Benchmarking

Run TPS benchmarks with:
```bash
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto --runs 3
```

Compare direct vs pipeline paths to identify overhead.
