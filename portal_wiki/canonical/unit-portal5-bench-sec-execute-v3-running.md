---
id: unit-portal5-bench-sec-execute-v3-running
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Running"
sources:
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: portal/modules/security/core/commands/run.py
last_generated_commit: 65958b7ff433a91759bbe4778df434a744fa802c
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.70703
updated_at: 1784946220.70703
---

The bench entry point is `python3 -m portal.modules.security.core`, which
dispatches through `portal/modules/security/core/__main__.py` into `cli.main`.
With no arguments it benches `DEFAULT_WORKSPACES` — the eight canonical
`auto-security::*` strings defined in `_data.py` — across every prompt in
`PROMPTS`, running the tool-free theory pass (prose rubric scoring via
`score_response`). The expensive passes are opt-in: `--exec-eval` enables the
tool-calling execution pass for the two `EXECUTION_WORKSPACES` entries,
`--exec-chain-models` adds the multi-model handoff chain, and `--lab-exec`
switches tool results from synthetic to real sandbox execution. `--dry-run`
prints the plan without calling the pipeline, and `--output` overrides the
default `results/sec_bench_<timestamp>.json` path.

## Why

The earlier prompt's "Running" section was an empty code block, so this unit
replaces it with the invocation that actually exists. The default is
deliberately broad (all workspaces across all prompts) while the slow and
lab-touching passes stay opt-in, so a quick dry-run and a full multi-hour live
campaign are both one command away without risking unintended live execution.
