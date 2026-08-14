---
id: unit-portal5-bench-execute-v4-phase-0-preflight-required-before-any-run
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Phase 0 \u2014 Preflight (required before\
  \ any run)"
sources:
- type: code
  path: scripts/execute_preflight.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.699662
updated_at: 1784946220.699662
---

```bash
python3 scripts/execute_preflight.py
```

Phase 0 is a hard requirement: run the preflight before anything else. It
prints the current production and eval workspace counts, the persona count,
the MCP fleet size, and the `model_pin` personas, and it exits nonzero with a
"STOP" banner if a retired alias id reappears in `config/portal.yaml`. Only
proceed to `--dry-run` and the real run once it reports "OK to run."

## Why

Preflight exists so the bench never starts from a stale or non-canonical
surface. Counts and vocabularies drift as workspaces and personas are added,
so an execution agent needs the current ground truth, not a doc's baked
numbers. The retired-alias check catches a regression where a retired id like
`auto-redteam` silently reappears; benching that surface would waste hours and
produce results that mislead, which is why the nonzero exit is a stop signal.
