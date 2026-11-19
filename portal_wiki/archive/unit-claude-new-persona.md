---
id: unit-claude-new-persona
historical: true
kind: why
title: "CLAUDE.md \u2014 New Persona"
sources:
- type: design
  path: CLAUDE.md
  section: New Persona
confidence: high
tags:
- claude
- architecture
- law

---

1. Create `config/personas/<slug>.yaml` with: `name`, `slug`, `module`, `workspace_model`, `category`, and one of `system_prompt`/`prompt_template`
2. `openwebui_init.py` creates the Open WebUI model preset on next seed
3. No other changes needed
4. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp
