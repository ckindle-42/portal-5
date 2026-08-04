---
id: unit-MCP_DEV_TOOLING-dual-mode-portal-vs-stock-no-file-renaming
kind: why
title: "MCP_DEV_TOOLING \u2014 Dual mode: Portal vs stock (no file renaming)"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: 'Dual mode: Portal vs stock (no file renaming)'
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.872641
updated_at: 1783195000.872641
---


Portal is the in-repo default — bare `opencode .` auto-discovers `opencode.jsonc`. To run
**stock** opencode (your normal cloud providers) while inside the repo, use the wrapper,
which points `OPENCODE_CONFIG` at your global config:

```bash
scripts/oc-portal.sh            # Portal: local pipeline backend (default)
scripts/oc-stock.sh             # stock: your global/cloud opencode config
scripts/oc-stock.sh --model anthropic/claude-sonnet-4-6   # extra args pass through
```

opencode has no `--strict` MCP bypass and merges configs by cwd, so if `oc-stock.sh` still
shows Portal models, run opencode from outside the repo (`cd ~ && opencode`) or set
`OC_GLOBAL_CONFIG=/path/to/your/opencode.json`. Neither mode renames or edits
`opencode.jsonc`.

---
