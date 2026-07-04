---
id: unit-claude-5-personas-live-in-config-personas
kind: why
title: "CLAUDE.md \u2014 5 \u2014 Personas Live in config/personas/"
sources:
- type: design
  path: CLAUDE.md
  section: "5 \u2014 Personas Live in config/personas/"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.807241
updated_at: 1783195000.807241
---


Each `.yaml` in `config/personas/` becomes an Open WebUI model preset during seeding. The YAML defines: `name`, `slug`, `system_prompt`, `workspace_model`, `category`. The `openwebui_init.py` script reads these and creates model presets in Open WebUI. Adding a new persona = adding one YAML file. See `config/personas/` for the full catalog (130 personas).
