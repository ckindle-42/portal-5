---
id: unit-HOWTO-6-security-analysis
kind: why
title: "HOWTO \u2014 6. Security Analysis"
sources:
- type: design
  path: docs/HOWTO.md
  section: 6. Security Analysis
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.841096
updated_at: 1783195000.841096
---


**What:** One base workspace (`auto-security`) covering research/simulation/execution tiers.
Since BUILD_PROGRAM_COLLAPSE_V1.md Phase 6, the former nine sibling workspaces (redteam,
blueteam, pentest, purpleteam×3, uncensored) are `?variant=` query params on `auto-security`
(or a persona's `variant:` field) instead of separate workspaces — same models, same tool
grants, just resolved via `_resolve_workspace_variant()` instead of a distinct workspace id.

| Variant | Tier | Model | Tools |
|---|---|---|---|
| *(base — no variant)* | Research | VulnLLM-R-7B (AppSec/CVE specialist) | web_search, web_fetch, classify_vulnerability, execute_python, execute_bash, kb_search |
| `uncensored` | Research | BaronLLM abliterated (no guardrails) | execute_bash, execute_python, remember, recall |
| `redteam` | Simulation | Qwen3.5-abliterated 9B | none |
| `redteam-deep` | Simulation | SuperGemma4-26B uncensored (deep) | none |
| `blueteam` | Research | Granite-4.1-8B (SOC triage, DFIR, ATT&CK) | web_search, web_fetch, classify_vulnerability, kb_search |
| `pentest` | Execution | Gemma-4-E2B-QAT abliterated | execute_bash, execute_python, web_search |
| `purpleteam` | Simulation, 2-hop | Qwen3.5-abliterated → Granite-4.1-8B | none |
| `purpleteam-deep` | Simulation, 4-hop | Qwen3.5-abliterated → Granite-4.1-8B → Qwen3-Coder-30B → Qwen3.6-27B | none |
| `purpleteam-exec` | Execution, 4-hop | SuperGemma4-26B (live exec) → same 3-hop detection/IR chain | execute_bash, execute_python, web_search |
