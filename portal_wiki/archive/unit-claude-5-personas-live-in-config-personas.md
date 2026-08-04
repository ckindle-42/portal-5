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
created_at: 1785348301.194338
updated_at: 1785348301.194338
---


Each `.yaml` in `config/personas/` becomes an Open WebUI model preset during seeding. The YAML defines: `name`, `slug`, `module`, `workspace_model`, `category`, and either `system_prompt` (inline) or `prompt_template` (a shared body under `portal/modules/eval/persona_matrix/prompts/<name>.txt` — exactly one of the two is required, see BUILD_PROGRAM_COLLAPSE_V1.md Phase 8). Optional `variant` selects a named override on a factored workspace (e.g. `auto-coding` + `variant: laguna`). Optional `model_pin` is an exact `config/backends.yaml` model id that **is consumed** — applied in the handler via `_resolve_model_override` (the same bounded, catalog-checked mechanism the `?model=<hint>` query param uses) — for a persona whose identity is tied to one specific model rather than its workspace's pool primary (see `DESIGN_PERSONA_INTENT_REMEDIATION_V1.md`). Optional `preferred_models` is an ordered model-fallback chain that is **NOT consumed anywhere in the serving path** — advisory metadata only, roadmapped for a future live chain-walk (`P5-FUT-MODEL-CHAINWALK`); do not treat it as selecting the served model, and do not set it alongside `model_pin` on the same persona (the pin is authoritative — two competing model-intent fields is how a persona can silently be served the wrong model, see `scripts/persona_intent_audit.py` Check 2/4). The `openwebui_init.py` script reads these and creates model presets in Open WebUI. Adding a new persona = adding one YAML file. See `config/personas/` for the full catalog — currently 138 files (`ls config/personas/*.yaml | wc -l`).
