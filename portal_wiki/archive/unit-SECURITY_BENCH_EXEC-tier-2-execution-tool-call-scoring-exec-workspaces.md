---
id: unit-SECURITY_BENCH_EXEC-tier-2-execution-tool-call-scoring-exec-workspaces
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Tier 2 \u2014 Execution (tool-call scoring, exec\
  \ workspaces only)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: "Tier 2 \u2014 Execution (tool-call scoring, exec workspaces only)"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.899394
updated_at: 1783195000.899394
---


Same prompts but with tools enabled on execution-capable workspaces. Scores tool call sequences against `exec_sequence` definitions. No lab dispatch — models generate tool calls, bench scores keywords.

```bash
python3 -m tests.benchmarks.bench_security \
  --workspaces auto-pentest auto-purpleteam-exec \
  --exec-eval \
  2>&1 | tee /tmp/secbench_exec.log
```
