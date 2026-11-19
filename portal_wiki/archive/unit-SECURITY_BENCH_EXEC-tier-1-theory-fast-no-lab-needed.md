---
id: unit-SECURITY_BENCH_EXEC-tier-1-theory-fast-no-lab-needed
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Tier 1: Theory (fast, no lab needed)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'Tier 1: Theory (fast, no lab needed)'
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

python3 -m tests.benchmarks.bench_security \
  --workspaces auto-security auto-redteam auto-redteam-deep auto-pentest auto-blueteam auto-purpleteam-exec \
  2>&1 | tee /tmp/secbench_theory.log
