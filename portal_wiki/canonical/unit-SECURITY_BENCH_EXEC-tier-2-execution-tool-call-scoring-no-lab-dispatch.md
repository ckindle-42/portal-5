---
id: unit-SECURITY_BENCH_EXEC-tier-2-execution-tool-call-scoring-no-lab-dispatch
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Tier 2: Execution (tool-call scoring, no lab dispatch)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'Tier 2: Execution (tool-call scoring, no lab dispatch)'
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.900136
updated_at: 1783195000.900136
---

python3 -m tests.benchmarks.bench_security \
  --workspaces auto-pentest auto-purpleteam-exec --exec-eval \
  2>&1 | tee /tmp/secbench_exec.log
