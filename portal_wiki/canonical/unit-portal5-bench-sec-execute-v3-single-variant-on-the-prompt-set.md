---
id: unit-portal5-bench-sec-execute-v3-single-variant-on-the-prompt-set
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Single variant on the prompt set"
sources:
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: config/portal.yaml
last_generated_commit: 9d387d9909cdcfc2c76b68bac06e77b1cd9088c2
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.707409
updated_at: 1784946220.707409
---

```bash
python3 -m portal.modules.security.core --workspaces auto-security::pentest
```

This benches a single variant across the full prompt set. The `pentest`
variant is defined under `config/portal.yaml`'s `auto-security.variants`, and
`auto-security::pentest` is one of the two `EXECUTION_WORKSPACES` in `_data.py`
(alongside `auto-security::purpleteam-exec`). With only `--workspaces` given,
this runs the theory pass — `tool_choice=none`, prose rubric scoring — for every
prompt; the tool-enabled execution pass requires adding `--exec-eval`, and
`--dry-run` prints the plan without hitting the pipeline.

## Why

A single-variant run is the cheapest way to smoke-test a new candidate model or
a changed prompt before committing hours to the full fleet. The variant still
resolves through the canonical `::` key, so routing, per-workspace timeouts, and
scoring all use the same vocabulary as a full multi-variant run.
