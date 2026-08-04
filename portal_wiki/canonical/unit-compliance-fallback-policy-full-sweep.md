---
id: unit-compliance-fallback-policy-full-sweep
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Full sweep"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5655859
updated_at: 1784946220.5655859
---

A full sweep runs every model in the auto-compliance chain against every applicable compliance scenario. The entrypoint is `tests/portal5_persona_matrix.py`, a thin shim for `portal.modules.eval.persona_matrix`. Without `--output`, the driver writes to `RESULTS_DIR` as `persona_matrix_<workspace>_<utc-stamp>.json`; an explicit `--output` path overrides the default. A complete run against the current chain:

```bash
python3 tests/portal5_persona_matrix.py \
    --output "tests/benchmarks/results/persona_matrix_$(date -u +%Y%m%dT%H%M%SZ).json"
```

Internally `run_sweep` resolves the chain with `chain_models_for_workspace`, loads the compliance personas, evicts Ollama models between cells, and returns a `portal5.persona_matrix.v1` report. `cli.py` returns exit code 1 when any cell has a FAIL (exit 2 when a baseline comparison also reports regressions), so a dirty sweep is visible to a shell.

## Why

The default filename embeds the workspace id because `RESULTS_DIR` is shared across every chain's sweeps; without the id an auto-compliance run and an auto-coding run would collide on the same timestamp. An explicit `--output` exists for operator-labelled runs, which is why the documented full-sweep command passes one, and the exit-code contract makes the sweep scriptable rather than eyeballed.
