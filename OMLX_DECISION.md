# OMLX Migration Decision (P5-FUT-013)

**Decision date:** 2026-04-24 (preliminary)
**Decision maker:** Operator (Chris)
**Bake-off period:** 2026-04-24 (initial smoke tests; full bake-off pending)
**Bake-off result files:** `tests/benchmarks/results/omlx_bakeoff_*.json`

## Decision

**HOLD** — Preliminary TPS tests show no significant OMLX advantage. KV cache persistence
(the headline feature) requires multi-turn TTFT measurement not yet performed.

## Evidence summary

### OMLX installation
- Installed from source: `github.com/jundot/omlx` v0.3.8.dev2
- Separate venv at `/Volumes/data01/omlx-venv` (isolated from mlx-proxy)
- Running on port 8085 alongside mlx-proxy on 8081
- 27 models discovered from HF cache via symlinks

### TPS comparison (isolated — full memory, one endpoint at a time)

| Model | mlx-proxy TPS | OMLX TPS | Delta |
|---|---|---|---|
| Llama-3.2-3B-Instruct-8bit | 58.8-60.2 | 56.8-57.2 | mlx-proxy ~4-5% faster |
| phi-4-8bit | 14.9-15.0 | 14.6 | mlx-proxy ~2-3% faster |

*Methodology: Each endpoint tested alone with full memory. Model loaded cold, then 3 steady-state
runs. 30s Metal reclaim wait between endpoint switches. Docker containers stopped during test.*

### TTFT on repeated context (5-turn conversation)

| Model | mlx-proxy TTFT | OMLX TTFT (cold) | OMLX TTFT (warm) | Delta (warm) |
|---|---|---|---|---|
| *(not yet measured — requires KV cache warm-up test)* | | | | |

### Concurrency (4 parallel requests)

| Model | mlx-proxy serial | OMLX concurrent | Throughput Delta |
|---|---|---|---|
| *(not yet measured)* | | | |

### Compatibility checks

- [x] OMLX installs and runs on port 8085 alongside mlx-proxy
- [x] 27/26 text-only MLX models discovered (26 MLX + draft models)
- [x] VLM models detected (7 VLM models auto-classified)
- [ ] Big-model evict mode equivalent — not tested
- [ ] Admission control — process memory limit set to 19.2GB (auto)
- [ ] qwen3_next architecture — not tested
- [ ] Tool-calling support — not tested

## Recommendation rationale

OMLX installed cleanly and runs alongside mlx-proxy without conflicts. With proper memory
isolation (one endpoint at a time, full memory available), mlx-proxy is 2-5% faster on TPS
for both small (Llama-3B) and medium (phi-4) models. The gap is narrower than initially
measured when both ran simultaneously (which showed 8-16% — unfair due to shared memory).

The headline OMLX feature is KV cache persistence across requests (TTFT drops from 30-90s
to 1-3s on repeated contexts). This requires testing with multi-turn conversations where
the same prefix is re-sent — NOT measured in these initial single-shot tests.

**Recommendation**: HOLD until full bake-off is run with:
1. KV cache warm-up TTFT measurement (the real value proposition)
2. Larger models (Qwen3-Coder-30B, Llama-3.3-70B) where caching matters most
3. Concurrent request handling comparison
4. Full model catalog compatibility verification

Track 1 speculative decoding provides independent TPS gains regardless of OMLX decision.

## Next steps

1. Run full M4-T08 bake-off with KV cache TTFT measurement
2. Test large models (Qwen3-Coder-30B, Llama-3.3-70B) on both endpoints
3. Measure multi-turn repeated-context TTFT difference
4. Finalize this document with REPLACE/AUGMENT/HOLD verdict
5. If REPLACE/AUGMENT: create `TASK_M4B_OMLX_MIGRATION.md`
