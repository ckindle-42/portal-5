---
id: unit-SEC_BENCH-quick-start-tiers
kind: what
title: 'Security bench quick-start: theory, exec, and lab-exec tiers'
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: ddb1cc61
- type: code
  path: portal/modules/security/core/cli.py
  commit: ddb1cc61
last_generated_commit: ddb1cc61
confidence: high
tags:
- security
- bench
- quickstart
created_at: 1784945192.269226
updated_at: 1784945192.269226
---

## Tier 1 — Theory (prose quality, all workspaces x all prompts)

Runs every prompt against every security workspace with tools disabled. Measures structure adherence, disclaimer density, MITRE coverage. No lab needed.

```bash
python3 -m portal.modules.security.core \
  --workspaces \
    auto-security auto-security::redteam auto-security::redteam-deep auto-security::pentest \
    auto-security::blueteam auto-security::purpleteam-exec \
  2>&1 | tee /tmp/secbench_theory.log
```

## Tier 2 — Execution (tool-call scoring, exec workspaces only)

Same prompts but with tools enabled on execution-capable workspaces. Scores tool call sequences against `exec_sequence` definitions. No lab dispatch.

```bash
python3 -m portal.modules.security.core \
  --workspaces auto-security::pentest auto-security::purpleteam-exec \
  --exec-eval \
  2>&1 | tee /tmp/secbench_exec.log
```

## Tier 3 — Lab-Exec (real dispatch against live lab)

Multi-model chain with real sandbox execution, blue defender, snapshot lifecycle, and lab probe. See the full command in the doc.
