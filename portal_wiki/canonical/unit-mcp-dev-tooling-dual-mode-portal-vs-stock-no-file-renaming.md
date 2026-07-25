---
id: unit-mcp-dev-tooling-dual-mode-portal-vs-stock-no-file-renaming
kind: what
title: "MCP_DEV_TOOLING \u2014 Dual mode: Portal vs stock (no file renaming)"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: 'Dual mode: Portal vs stock (no file renaming)'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.575579
updated_at: 1784946220.575579
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
