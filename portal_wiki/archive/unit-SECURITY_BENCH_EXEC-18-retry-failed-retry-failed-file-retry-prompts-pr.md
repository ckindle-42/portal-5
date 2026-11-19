---
id: unit-SECURITY_BENCH_EXEC-18-retry-failed-retry-failed-file-retry-prompts-pr
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 18. Retry Failed (`--retry-failed FILE`, `--retry-prompts\
  \ PROMPT`)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 18. Retry Failed (`--retry-failed FILE`, `--retry-prompts PROMPT`)
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

Reads a previous result JSON, identifies failures (chain depth < max, success_rate < 0.5), and re-runs only the failed prompts. `--retry-prompts` targets specific prompts regardless of previous results.

```bash
