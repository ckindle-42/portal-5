---
id: unit-MCP_DEV_TOOLING-workspace-selection
kind: why
title: "MCP_DEV_TOOLING \u2014 Workspace selection"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: Workspace selection
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.872401
updated_at: 1783195000.872401
---


```bash
opencode .                                          # default: portal/auto-coding-agentic (Laguna-XS.2 33B)
opencode . --model portal/auto-agentic              # heavy 80B MoE for complex multi-file refactors
opencode . --model portal/auto-agentic-lite         # AgentWorld 35B direct (lighter load, 45 t/s)
opencode . --model portal/auto-agentic-ornith       # Ornith-1.0-35B direct — agentic option, not a replacement
opencode . --model portal/auto-coding               # one-shot code generation (Qwen3-Coder 30B)
opencode . --model portal/auto-coding-northmini     # North-Mini-Code 30B-A3B — coding diversity option
opencode . --model portal/auto-reasoning            # deep reasoning for architectural decisions
opencode . --model portal/auto-security             # defensive security code review
opencode . --model portal/auto-pentest              # authorized penetration testing assistance
opencode . --model portal/auto-purpleteam-exec      # tool-calling security with live lab access
opencode . --model portal/auto-data                 # data science, SQL, analysis
opencode . --model portal/auto-research             # web-augmented research and summarization
```

Run `opencode models` to list all 94 available workspaces.
