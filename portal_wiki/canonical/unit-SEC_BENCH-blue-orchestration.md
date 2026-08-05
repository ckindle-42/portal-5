---
id: unit-SEC_BENCH-blue-orchestration
kind: what
title: Blue/purple discovery orchestration modes
sources:
- type: code
  path: portal/modules/security/core/blue.py
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- bench
- orchestration
- security
- verified-v1
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

`scripted` and `hybrid` are assisted diagnostics and do not produce a primary
capability score. `orchestrated`, `orchestrated-2section`, `council`, and
`multichain` are standalone modes that replay a captured red episode
(`--replay-captured-red`) rather than `--purple` prompt variants.

## Three-section pipeline (`orchestrated`)

Retriever gathers telemetry; Hunter forms hypotheses; Expert renders verdict.

## Council of Agreement (`council`)

One Retriever gathers evidence once; N reasoning members vote independently.

## Multi-chain analyst (`multichain`)

N fully independent investigative chains. Consolidation routes to: `AUTO_CONFIRM`, `ESCALATE`, `CONFIRM_AND_ESCALATE`, `DISMISS`.

Escalation is a SCORED win, not a miss.

## Why

The mode table exists because a single blue prompt cannot serve every evaluation question. Scripted and discovery measure a lone defender; orchestrated, council, and multichain isolate how multiple models split evidence gathering from verdicts. The default is discovery so an operator who omits the flag gets the least-leading evaluation, while the standalone modes intentionally require a captured episode so comparisons stay reproducible against the same red evidence.
