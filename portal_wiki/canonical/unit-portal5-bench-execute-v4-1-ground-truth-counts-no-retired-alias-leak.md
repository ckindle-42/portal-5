---
id: unit-portal5-bench-execute-v4-1-ground-truth-counts-no-retired-alias-leak
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 1. Ground truth \u2014 counts + no retired-alias\
  \ leak"
sources:
- type: code
  path: scripts/execute_preflight.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.7000399
updated_at: 1784946220.7000399
---

```bash
python3 scripts/execute_preflight.py
```

The preflight is the ground-truth gate for every bench, security, and
acceptance session. It recomputes the production and eval workspace counts,
the persona count, the MCP fleet size, and the `model_pin` personas from live
YAML at run time, then returns zero only when no retired alias id reappears in
`config/portal.yaml`. A nonzero exit with the "STOP" banner means the surface
regressed and the suite must not run.

## Why

This suite's scale is config-driven and drifts, so baked workspace or persona
counts in an execution doc went stale and mis-planned runs. The preflight
recomputes reality from `config/portal.yaml` at run time and hard-fails on a
retired alias like `auto-redteam` or `auto-phi4` reappearing, which would
silently corrupt a whole bench. Trust its numbers, never the doc.
