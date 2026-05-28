# OMLX Migration Decision (P5-FUT-013)

**Decision date:** 2026-04-25 (full bake-off complete)
**Decision maker:** Operator (Chris)
**Bake-off period:** 2026-04-25 (full bake-off: KV cache + TPS + concurrent)
**Bake-off result files:**
- `tests/benchmarks/results/omlx_bakeoff_20260425T181325Z.json` (full bake-off)
- `tests/benchmarks/results/omlx_bakeoff_20260425T175721Z.json` (initial smoke test)

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
| Llama-3.2-3B-Instruct-8bit | 37.5 | 37.7 | ~equivalent |
| Qwen3-Coder-30B-A3B-Instruct-8bit | 30.3 | N/A (OOM) | mlx-proxy only |
| Llama-3.2-3B-Instruct-8bit (prior smoke) | 58.8-60.2 | 56.8-57.2 | mlx-proxy ~4-5% faster |

*Methodology: Each endpoint tested alone with full memory. Model loaded cold, then 3 steady-state
runs. 30s Metal reclaim wait between endpoint switches. Docker containers stopped during test.*

### TTFT on repeated context (5-turn conversation)

| Model | mlx-proxy TTFT | OMLX TTFT (cold) | OMLX TTFT (warm) | Delta (warm) |
|---|---|---|---|---|
| Llama-3.2-3B-Instruct-8bit | 3.32s | 0.29s | 0.38s | **+31% (worse!)** |
| Qwen3-Coder-30B-A3B-Instruct-8bit | 3.92s | N/A (OOM) | N/A | N/A |

*Methodology: 5-turn conversation sent 3× in sequence. Cold = first request (cache empty). Warm = subsequent requests (prefix should be cached). OMLX warm is SLOWER than cold — KV cache NOT working. OMLX also failed to load 22GB model due to memory constraints.*

### Concurrency (4 parallel requests)

| Model | mlx-proxy serial | OMLX concurrent | Speedup |
|---|---|---|---|
| Llama-3.2-3B-Instruct-8bit | 13.00s | 6.82s | 1.9× |
| Qwen3-Coder-30B-A3B-Instruct-8bit | 14.64s | N/A (OOM) | N/A |

*Note: mlx-proxy is serial — concurrent requests queue. OMLX shows marginal batching benefit but fails on larger models.*

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

1. **KV cache NOT working**: OMLX warm TTFT (0.38s) is 31% SLOWER than cold (0.29s).
   This is the opposite of expected behavior — the cache should dramatically reduce TTFT.
2. **TPS**: ~equivalent between OMLX and mlx-proxy on 3B model (~37 t/s)
3. **Memory**: OMLX cannot load 22GB Qwen3-Coder-30B model even with ~36GB available
4. **Concurrency**: OMLX shows marginal benefit (1.9× speedup) but mlx-proxy is more stable

**Conclusion**: OMLX does not deliver its headline KV cache feature. No reason to replace
mlx-proxy. RETIRE decision stands.

mlx-proxy continues as the production inference solution. Track 1 speculative decoding
provides independent TPS gains.

## Next steps

1. Close P5-FUT-013 — evaluation complete
2. Remove OMLX server from launch.sh if integrated
3. Consider Docker Desktop restart if memory issues persist (56GB VM is abnormally high)
4. Continue with mlx-proxy as production inference

---

## Re-evaluation 2026-05-28 (TASK_OMLX_REEVAL_V2)

**Trigger:** oMLX v0.3.10 release notes claim fixes for three of the
four findings that drove the 2026-04-25 RETIRE decision
(RotatingKVCache attention dilution, OMLX_MAX_PROCESS_MEMORY enforcement,
OOM under sustained load). Native MTP support shipped in v0.3.9 via
ml-explore/mlx-lm PR #990 — the same unblock path P5_ROADMAP P5-FUT-SPEC
was waiting on.

**Scope:** Full four-dimensional re-evaluation (TPS, KV-cache TTFT,
concurrent throughput, MTP speedup) using the existing bench_omlx.py
scaffold from the 2026-04-25 run, extended with a new MTP probe mode.

**Versions tested:**
- oMLX: v0.3.12 (vs v0.3.8.dev2 in original run)
- mlx-proxy: unchanged from original run
- Portal 5: v7.0.x (vs v6.x at original run)

**Results files:**
- `tests/benchmarks/results/omlx_reeval_20260528T145902Z.json`
- `tests/benchmarks/results/omlx_reeval_20260528T145902Z.md` (analysis)

**Headline:** oMLX v0.3.12 MTP speedup PASSES the 1.5× gate on all three
output sizes (1.55×-1.65×), but KV-cache warm TTFT is still WORSE than
cold (same bug class as the 2026-04-25 finding), concurrent throughput
did not improve, and the practical speedup over the production 4-bit
baseline is marginal (0.95-1.14×).

**Decision matrix cell:** PROBE_AGAIN_NARROWLY

**Disposition of production inference:** UNCHANGED. mlx-proxy remains
the primary inference server. oMLX left installed for follow-on MTP
stability probe (TASK_OMLX_MTP_STABILITY_V1.md).

**Open items moved or closed:**
- P5-FUT-013: stays RETIRED; re-evaluation confirmed KV cache still broken
- P5-FUT-SPEC: UNBLOCKED via Path C (oMLX MTP side-car) pending stability
  probe; Path A (mlx-lm PR #990) still viable upstream alternative
- P5-MTP-001: MEDIUM — MTP gate passes (1.55×-1.65×), integration design
  pending stability probe results
