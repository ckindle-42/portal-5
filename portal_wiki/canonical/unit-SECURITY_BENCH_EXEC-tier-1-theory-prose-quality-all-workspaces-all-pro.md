---
id: unit-SECURITY_BENCH_EXEC-tier-1-theory-prose-quality-all-workspaces-all-pro
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Tier 1 \u2014 Theory (prose quality, all workspaces\
  \ \xD7 all prompts)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: "Tier 1 \u2014 Theory (prose quality, all workspaces \xD7 all prompts)"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.8991292
updated_at: 1783195000.8991292
---


Runs every prompt against every security workspace with tools disabled. Measures structure adherence, disclaimer density, MITRE coverage. No lab needed.

```bash
python3 -m tests.benchmarks.bench_security \
  --workspaces \
    auto-security auto-redteam auto-redteam-deep auto-pentest \
    auto-blueteam auto-purpleteam-exec \
  2>&1 | tee /tmp/secbench_theory.log
```
