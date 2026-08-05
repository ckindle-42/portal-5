---
id: unit-portal5-bench-sec-execute-v3-several-variants
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Several variants"
sources:
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/security/core/commands/run.py
last_generated_commit: 9a62300d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.707802
updated_at: 1784946220.707802
---

```bash
python3 -m portal.modules.security.core --workspaces \
    auto-security::redteam auto-security::blueteam auto-security::purpleteam
```

This form benches three canonical variants — `redteam`, `blueteam`, and
`purpleteam` — each across the full prompt set. All three are defined as
`variants:` sub-blocks of `auto-security` in `config/portal.yaml`, so each
resolves to a distinct routed model configuration rather than the base
workspace. The `--workspaces` flag accepts any number of ids (nargs="+"),
defaults to `DEFAULT_WORKSPACES` when omitted, and `run_bench` cross-filters the
prompt categories: a blue-team workspace skips red-team prompts and vice versa.
Run with `--dry-run` first to confirm the resolved set before any live call.

## Why

Benching several variants in one invocation is the standard
candidate-comparison shape: identical prompts and scoring, only the served
model differs. The cross-category skip in `run_bench` matters because a blueteam
variant handed offensive prompts would score against the wrong rubric, so the
harness removes that mismatch deterministically before any model is called.
