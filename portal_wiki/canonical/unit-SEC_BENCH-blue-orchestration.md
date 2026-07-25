---
id: unit-SEC_BENCH-blue-orchestration
kind: what
title: Blue/purple discovery orchestration modes
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: ddb1cc61
- type: code
  path: portal/modules/security/core/blue.py
  commit: ddb1cc61
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
  commit: ddb1cc61
last_generated_commit: ddb1cc61
confidence: high
tags:
- security
- bench
- orchestration
created_at: 1784945480.186831
updated_at: 1784945480.186831
---

`--blue-mode` selects which blue investigation path a run uses:

| Mode | Shape | Prompt |
|---|---|---|
| `scripted` | 1 model, tools | Mandatory step checklist |
| `discovery` (default) | 1 model, tools | Fully open-ended, no hints |
| `hybrid` | 1 model, tools | Open-ended with technique-reference hints |
| `orchestrated` | 3 sections | tool + reasoning + expert |
| `orchestrated-2section` | 2 sections | tool + merged reasoning/expert |
| `council` | tool + N reasoning + arbiter | N interpreters vote over shared evidence |
| `multichain` | N independent chains | N fully independent investigations

## Three-section pipeline (`orchestrated`)

Retriever gathers telemetry; Hunter forms hypotheses; Expert renders verdict.

## Council of Agreement (`council`)

One Retriever gathers evidence once; N reasoning members vote independently.

## Multi-chain analyst (`multichain`)

N fully independent investigative chains. Consolidation routes to: `AUTO_CONFIRM`, `ESCALATE`, `CONFIRM_AND_ESCALATE`, `DISMISS`.

Escalation is a SCORED win, not a miss.
