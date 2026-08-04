---
id: unit-SECURITY_BENCH_EXEC-18-retry-failed-retry-failed-file-retry-prompts-pr
kind: why
title: "SECURITY_BENCH_EXEC \u2014 18. Retry Failed (`--retry-failed FILE`, `--retry-prompts\
  \ PROMPT`)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 18. Retry Failed (`--retry-failed FILE`, `--retry-prompts PROMPT`)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.905824
updated_at: 1783195000.905824
---

Reads a previous result JSON, identifies failures (chain depth < max, success_rate < 0.5), and re-runs only the failed prompts. `--retry-prompts` targets specific prompts regardless of previous results.

```bash
