---
id: unit-compliance-fallback-policy-granite-required-sweep-fails-if-granite-has-been-removed-from-chain
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Granite-required sweep (fails if Granite\
  \ has been removed from chain)"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: tests/persona_matrix_diff.py
- type: code
  path: config/backends.yaml
last_generated_commit: 1ed83b22525c97ed996c835b7519e10c75d13ad0
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5660539
updated_at: 1784946220.5660539
---

The `--require` flag makes a sweep fail fast when a named model is absent from the resolved chain. In `run_sweep`, after backend, model and big-model filters, every required substring must appear in some chain model id; otherwise the driver prints the missing list and exits 3 before any cell runs. The documented granite-required sweep:

```bash
python3 tests/portal5_persona_matrix.py \
    --backend ollama \
    --require granite4.1:8b,granite4.1:30b \
    --output "tests/benchmarks/results/persona_matrix_granite_$(date -u +%Y%m%dT%H%M%SZ).json"
```

Both granite models are currently registered in the reasoning and general groups of `config/backends.yaml`, so the auto-compliance chain contains them; the sweep fails only if no remaining chain id contains the required substring. Comparison against baseline uses the real diff tool rather than a hand-rolled snippet:

```bash
python3 tests/persona_matrix_diff.py \
    tests/benchmarks/results/persona_matrix_baseline_auto-compliance.json \
    tests/benchmarks/results/persona_matrix_<NEW>.json --threshold 10
```

`compute_regressions` treats PASS-rate as PASS over PASS plus WARN plus FAIL per cell and flags a drop beyond the threshold in percentage points, default 10.0. The driver's `--baseline-compare` runs the same comparison inline and exits non-zero on regressions.

## Why

The source doc shipped an inline diff snippet with a hardcoded five-point flag that never matched the driver's real regression machinery. The code paths that actually enforce a granite-required sweep are the substring check in `run_sweep` (exit 3) and the per-cell PASS-rate comparison in `persona_matrix_diff` (10pp default), and grounding the unit to those two entry points keeps the failure mode and comparison semantics exact.
