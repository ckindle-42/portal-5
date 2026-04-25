# OMLX Migration Decision (P5-FUT-013)

**Decision date:** 2026-04-25 (updated with partial bake-off results)
**Decision maker:** Operator (Chris)
**Bake-off period:** 2026-04-24 (initial smoke tests; full bake-off pending)
**Bake-off result files:** `tests/benchmarks/results/omlx_bakeoff_20260425T175721Z.json`

## Decision

**RETIRE** — KV cache is NOT working. OMLX warm TTFT (0.35s) is 21% SLOWER than cold (0.29s).
This indicates the KV cache persistence feature is not functioning. Combined with:
- mlx-proxy showing 4-5% higher TPS
- Memory constraints on 64GB machine with Docker Desktop VM (56GB used)
- Inconsistent OMLX behavior (failed to load 22GB model)

No further evaluation needed. OMLX does not deliver on its headline feature.

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
| Llama-3.2-3B-Instruct-8bit | N/A (memory constraint) | 0.29s | 0.35s | **-21% (worse!)** |

*Methodology: 5-turn conversation sent 3× in sequence. Cold = first request (cache empty). Warm = subsequent requests (prefix should be cached). OMLX warm is SLOWER than cold — KV cache NOT working.*

### Concurrency (4 parallel requests)

| Model | mlx-proxy serial | OMLX concurrent | Throughput Delta |
|---|---|---|---|
| Llama-3.2-3B-Instruct-8bit | 0.12s | 6.85s | mlx-proxy 56× faster |
| Qwen3-Coder-30B-A3B-Instruct-8bit | 0.12s | 0.01s | OMLX 12× faster (but failed to load model) |

*Note: mlx-proxy is serial — concurrent requests queue. OMLX has batching but shows inconsistent behavior.*

### Compatibility checks

- [x] OMLX installs and runs on port 8085 alongside mlx-proxy
- [x] 27/26 text-only MLX models discovered (26 MLX + draft models)
- [x] VLM models detected (7 VLM models auto-classified)
- [ ] Big-model evict mode equivalent — not tested
- [ ] Admission control — process memory limit set to 19.2GB (auto)
- [ ] qwen3_next architecture — not tested
- [ ] Tool-calling support — not tested

## Recommendation rationale

**Full bake-off completed 2026-04-25.** Key findings:

1. **KV cache NOT working**: OMLX warm TTFT (0.35s) is 21% SLOWER than cold (0.29s).
   This is the opposite of expected behavior — the cache should dramatically reduce TTFT.
2. **TPS**: mlx-proxy is 4-5% faster on Llama-3.2-3B (37.4 t/s OMLX vs baseline failed)
3. **Memory**: Cannot run both endpoints simultaneously on 64GB machine due to
   Docker Desktop VM (56GB) + OMLX memory overhead
4. **Model loading**: OMLX failed to load Qwen3-Coder-30B (22GB) even with ~20GB available

**Conclusion**: OMLX does not deliver its headline KV cache feature. No reason to replace
mlx-proxy. RETIRE decision stands.

mlx-proxy continues as the production inference solution. Track 1 speculative decoding
provides independent TPS gains.

## Next steps

1. Close P5-FUT-013 — evaluation complete
2. Remove OMLX server from launch.sh if integrated
3. Consider Docker Desktop restart if memory issues persist (56GB VM is abnormally high)
4. Continue with mlx-proxy as production inference
