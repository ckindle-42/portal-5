# TASK: OMLX MTP Stability Probe (SKELETON)

**Predecessor:** TASK_OMLX_REEVAL_V2 (decision cell: PROBE_AGAIN_NARROWLY)
**Status:** SKELETON — design before execution

## Scope

MTP-only sub-probe: 100+ sequential requests at long output size
through oMLX with MTP enabled, recording every error, every timeout,
every output anomaly. The single-shot v2 run showed MTP gain but did
not exercise sustained load.

## Pass criterion

- ≥98% successful response rate over 100+ requests
- No oMLX crashes over 100 requests
- Maintained MTP speedup (no degradation in last 25 requests vs first 25)
- No empty outputs

## Design

- Target model: `Jundot/Qwen3.6-27B-oQ8-mtp` on oMLX :8085
- Output size: 2048 tokens (long — maximizes MTP benefit)
- Temperature: 0 (deterministic, lossless speculative decoding)
- Prompt: cycling through 5 diverse coding prompts to avoid KV cache artifacts
- Cooldown: 5s between requests
- Log capture: full oMLX log for the run duration
- Metrics: per-request TPS, elapsed, output tokens, error (if any)
- Baseline comparison: first 25 requests vs last 25 requests (median TPS)

## Files

- Script: `tests/benchmarks/bench_omlx_stability.py` (new)
- Results: `tests/benchmarks/results/omlx_mtp_stability_<ts>.json`
- Analysis: inline in the results JSON

## Out of scope

- KV cache testing (known broken, separate issue)
- Concurrent throughput (oMLX batching not competitive on M4 Pro)
- Different models or quantization levels
- Promotion decision (this is evidence-gathering only)

## Promotion path

If this probe passes:
1. Write TASK_OMLX_MTP_PROMOTE_V1.md (integration design)
2. Promote P5-MTP-001 from MEDIUM to HIGH
3. Consider oMLX as side-car for long-output coding workspaces

If this probe fails:
1. Update KNOWN_LIMITATIONS.md with instability finding
2. Revert P5-MTP-001 to LOW
3. Re-evaluate at oMLX v0.4.x or Mac Studio hardware tier
