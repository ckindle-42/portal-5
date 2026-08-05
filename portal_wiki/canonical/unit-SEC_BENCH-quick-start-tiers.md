---
id: unit-SEC_BENCH-quick-start-tiers
kind: what
title: 'Security bench quick-start: theory, exec, and lab-exec tiers'
sources:
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/_data.py
last_generated_commit: 26f31124
claims: []
confidence: high
tags:
- bench
- quickstart
- security
- verified-v1
created_at: 1784945192.269226
updated_at: 1784945192.269226
---

## Tier 1 — Theory (prose quality, workspace prompts only)

Runs the prompt set against the listed security workspaces with tools disabled. Measures structure adherence, disclaimer density, MITRE coverage. No lab needed.

```bash
python3 -m portal.modules.security.core \
  --workspaces \
    auto-security auto-security::redteam auto-security::redteam-deep auto-security::pentest \
    auto-security::blueteam auto-security::purpleteam-exec \
  2>&1 | tee /tmp/secbench_theory.log
```

## Tier 2 — Execution (tool-call scoring, exec workspaces only)

Same prompts but with tools enabled on the execution-capable workspaces. Scores tool call sequences against `exec_sequence` definitions. No lab dispatch.

```bash
python3 -m portal.modules.security.core \
  --workspaces auto-security::pentest auto-security::purpleteam-exec \
  --exec-eval \
  2>&1 | tee /tmp/secbench_exec.log
```

## Tier 3 — Lab-Exec (real dispatch against live lab)

Multi-model chain with real sandbox execution, blue defender, snapshot lifecycle, and lab probe: `--skip-workspace-bench --exec-chain-models <roster> --blue-defender-model <model> --prompt <key> --lab-exec` (a concrete command is in `unit-SEC_BENCH-single-prompt-tests`).

## Why

These three tiers are the same bench at increasing cost and fidelity, and the quick-start framing exists so an operator can pick the cheapest tier that answers the current question. Theory validates many models quickly, exec adds tool-call sequence without lab dependencies, and lab-exec is reserved for runs whose results must be trusted as real. The `--exec-eval` flag is what switches exec workspaces into tier two, which is why it appears in exactly that command.
