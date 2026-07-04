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


**What:** Nine security-focused workspaces across three tiers — simulation, research, and execution.

| Workspace | Tier | Model | Tools |
|---|---|---|---|
| `auto-security` | Research | VulnLLM-R-7B (AppSec/CVE specialist) | web_search, web_fetch, classify_vulnerability, execute_python, execute_bash, kb_search |
| `auto-security-uncensored` | Research | VulnLLM-R-7B (no guardrails) | web_search, kb_search |
| `auto-redteam` | Simulation | Qwen3.5-abliterated 9B | none |
| `auto-redteam-deep` | Simulation | SuperGemma4-26B uncensored (0.915 bench) | none |
| `auto-blueteam` | Research | sylink:8b (SOC triage, DFIR, ATT&CK) | web_search, web_fetch, classify_vulnerability, kb_search |
| `auto-pentest` | Execution | Gemma4-E2B-QAT abliterated (~3GB, thinking model) | execute_bash, execute_python, web_search |
| `auto-purpleteam` | Simulation | Qwen3.5-abliterated → Foundation-Sec-8B | none |
| `auto-purpleteam-deep` | Simulation | 4-hop chain (red→blue→detect→IR) | none |
| `auto-purpleteam-exec` | Execution | 4-hop chain, primary has live execution | execute_bash, execute_python, web_search |
