---
id: unit-claude-new-persona
kind: why
title: "CLAUDE.md \u2014 New Persona"
sources:
- type: design
  path: CLAUDE.md
  section: New Persona
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.810024
updated_at: 1783195000.810024
---

1. Create `config/personas/<slug>.yaml` with: `name`, `slug`, `system_prompt`, `workspace_model`, `category`
2. `openwebui_init.py` creates the Open WebUI model preset on next seed
3. No other changes needed
