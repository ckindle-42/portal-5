---
id: unit-HOWTO-4-personas
kind: why
title: "HOWTO \u2014 4. Personas"
sources:
- type: design
  path: docs/HOWTO.md
  section: 4. Personas
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.839925
updated_at: 1783195000.839925
---

**What:** Pre-configured specialist prompts that shape the AI's behavior.

**How:** Select a persona from the model dropdown alongside workspaces.

**Available personas:** use `unit-fact-persona-roster` for the generated live
count, module ownership, workspace binding, and model pins. Do not maintain a
second handwritten roster here.

To inspect the live module breakdown:

```bash
python3 -m portal.platform.inference.cli module list
```

**Example — red team:**

1. Select `Red Team Operator`.
2. Ask for an attack-surface analysis or lab-scoped exercise.
3. Its `workspace_model: auto-security` and `variant: redteam` select the
   corresponding security route.

**Verify personas exposed by the pipeline:**

```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
  | python3 -c "import sys,json; [print(m['name']) for m in json.load(sys.stdin)['data']]"
```
