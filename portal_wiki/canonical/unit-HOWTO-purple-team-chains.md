---
id: unit-HOWTO-purple-team-chains
kind: why
title: "HOWTO \u2014 Purple Team Chains"
sources:
- type: design
  path: docs/HOWTO.md
  section: Purple Team Chains
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.84208
updated_at: 1783195000.84208
---


Purple team workspaces run multi-hop chains — red team output feeds directly into blue team analysis.

**`auto-security` `?variant=purpleteam`** (2-hop, ~3 min):
```
Attack scenario: AWS S3 bucket misconfiguration allowing public read access
```
1. Hop 1 — Qwen3.5-abliterated: attack vectors, exploitation, persistence
2. Hop 2 — Foundation-Sec-8B-Reasoning: detection, IOCs, mitigations

**`auto-security` `?variant=purpleteam-deep`** (4-hop, ~10-15 min):
Same as above plus:
3. Hop 3 — Qwen3-Coder: Sigma rules, Wazuh XML, hunting queries
4. Hop 4 — Qwen3.6-27B: full IR playbook (triage → containment → recovery)

**`auto-security` `?variant=purpleteam-exec`** (4-hop with live execution, authorized targets only):
Primary hop has `execute_bash`/`execute_python` — actually runs enumeration and PoC commands, passes real output through the detection/IR chain.
