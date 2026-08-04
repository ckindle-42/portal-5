---
id: unit-portal5-bench-execute-v4-portal5-bench-execute-v4-opencode-bench-execution-prompt
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 PORTAL5_BENCH_EXECUTE_V4 \u2014 opencode Bench\
  \ Execution Prompt"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: tests/benchmarks/bench_tps.py
- type: code
  path: tests/benchmarks/bench/cli.py
- type: code
  path: scripts/update_grafana_benchmarks.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.6987362
updated_at: 1784946220.6987362
---

> **Supersedes** `PORTAL5_BENCH_EXECUTE_V3.md` (archived under
> `docs/_archive_execdocs/`). V4 is the current opencode bench execution
> prompt for the post-collapse / post-alias-retirement codebase: corrected
> scale, `PORTAL_ENABLE_EVAL` gating, preflight-driven counts (no baked
> numbers), and served-model verification tie-in.

Run the Portal 5 comprehensive TPS benchmark suite (Ollama-only). The live
stack is expected running when you begin. At the end, update the Grafana
benchmarks dashboard and commit results.

**Scale is config-driven and drifts — never trust a number in this doc. Run
the preflight first:**

```bash
python3 scripts/execute_preflight.py
```

`bench_tps.py` is the sole TPS instrument. The acceptance and UAT suites
assert no performance numbers — they delegate routing/TPS coverage to the
bench.

## Why

V4 exists because the pre-collapse docs baked in counts that went stale after
alias retirement and the eval-module gating changed how the bench surface is
loaded. The execution prompt now points at `scripts/execute_preflight.py` for
ground truth and at `bench_tps.py --dry-run` for the plan, so an execution
agent derives numbers from live config instead of a paragraph. `bench_tps.py`
is a re-export shim over `tests/benchmarks/bench/`, keeping the operator
entry point stable while the implementation was modularized.
