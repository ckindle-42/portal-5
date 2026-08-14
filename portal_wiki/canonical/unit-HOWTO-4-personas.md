---
id: unit-HOWTO-4-personas
kind: why
title: "HOWTO \u2014 4. Personas"
sources:
- type: code
  path: config/personas/redteamoperator.yaml
- type: code
  path: scripts/openwebui_init.py
- type: code
  path: portal/platform/inference/router/preinject.py
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.839925
updated_at: 1783195000.839925
---

**What:** Pre-configured specialist prompts that shape the AI's behavior.

**How:** Personas live as one YAML file each under `config/personas/`. During seeding, `scripts/openwebui_init.py` reads them and creates model presets in Open WebUI, binding each persona to a `workspace_model` and an optional `variant`. Select a persona from the model dropdown alongside workspaces.

**Available personas:** use `unit-fact-persona-roster` for the generated live count, module ownership, workspace binding, and model pins. Do not maintain a second handwritten roster here.

To inspect the live module breakdown:

```bash
python3 -m portal.platform.inference.cli module list
```

**Example — red team:**

1. Select `Red Team Operator`.
2. Ask for an attack-surface analysis or lab-scoped exercise.
3. `config/personas/redteamoperator.yaml` declares `workspace_model: auto-security` and `variant: redteam`; the pipeline resolves the variant through `_resolve_workspace_variant` in `portal/platform/inference/router/preinject.py`, applying `auto-security`'s redteam variant model, prompt, and empty tool grant.

**Verify personas exposed by the pipeline:**

```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
  | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['data']]"
```

`PIPELINE_API_KEY` lives in `.env` (auto-generated on first `up`); the pipeline's `list_models` handler (`portal/platform/inference/router/handlers.py`) serves workspaces plus the IDE-curated persona entries so external pickers agree with Open WebUI.

## Why

Personas are data, not code: one YAML per persona means adding a specialist never touches the pipeline, and the workspace-model binding guarantees a persona is always served by the model family it was written for. Routing a persona through a workspace variant rather than a standalone workspace keeps model, prompt, tool grants, and guardrail posture in one place instead of duplicating them across near-identical workspaces.
