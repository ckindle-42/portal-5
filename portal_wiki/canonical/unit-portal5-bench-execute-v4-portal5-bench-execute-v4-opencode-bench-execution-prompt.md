---
id: unit-portal5-bench-execute-v4-portal5-bench-execute-v4-opencode-bench-execution-prompt
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 PORTAL5_BENCH_EXECUTE_V4 \u2014 opencode Bench\
  \ Execution Prompt"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: "PORTAL5_BENCH_EXECUTE_V4 \u2014 opencode Bench Execution Prompt"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6987362
updated_at: 1784946220.6987362
---

> **Supersedes** `PORTAL5_BENCH_EXECUTE_V3.md` (archive it to
> `docs/_archive_execdocs/`). V4 updates for the post-collapse / post-alias-
> retirement codebase (HEAD `87b19bf`): corrected scale, `PORTAL_ENABLE_EVAL`
> gating, preflight-driven counts (no baked numbers), and served-model
> verification tie-in.

Run the Portal 5 comprehensive TPS benchmark suite (Ollama-only). The live
stack is expected running when you begin. At the end, update the Grafana
benchmarks dashboard and commit results.

**Scale is config-driven and drifts — never trust a number in this doc. Run the
preflight first:**

```bash
python3 scripts/execute_preflight.py
```

As of HEAD `87b19bf` it reports **21 production workspaces, 60 eval/bench
workspaces, 138 personas, 114 Ollama models**. `bench_tps.py --dry-run`
translates that to **~273 tests (mode=all)**. These will change; the preflight
and `--dry-run` are the source of truth, not this paragraph.

`bench_tps.py` is the sole TPS instrument. The acceptance and UAT suites assert
no performance numbers.

---
