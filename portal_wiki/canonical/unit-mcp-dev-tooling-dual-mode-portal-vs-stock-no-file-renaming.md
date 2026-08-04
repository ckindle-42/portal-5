---
id: unit-mcp-dev-tooling-dual-mode-portal-vs-stock-no-file-renaming
kind: what
title: "MCP_DEV_TOOLING \u2014 Dual mode: Portal vs stock (no file renaming)"
sources:
- type: code
  path: scripts/oc-portal.sh
- type: code
  path: scripts/oc-stock.sh
- type: code
  path: opencode.jsonc
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.575579
updated_at: 1784946220.575579
---

opencode runs in Portal mode by default inside the repo: bare `opencode .` reads
`opencode.jsonc` and gets the local pipeline backend plus the `mcp` roster.
`scripts/oc-portal.sh` is the explicit Portal wrapper; `scripts/oc-stock.sh` runs
stock opencode by exporting `OPENCODE_CONFIG` pointing at the global config, which
overrides the project provider without touching any file. If Portal models still
appear after that, the wrapper's own notes recommend running opencode from outside
the repo or setting `OC_GLOBAL_CONFIG`. Neither mode renames or edits
`opencode.jsonc`.

## Why

opencode has no strict-MCP flag and merges configs by working directory, so the only
clean way to get stock behaviour inside the repo is to force the global config into
play. Wrapping that in a script, and leaving the project config untouched, gives the
operator a reversible switch instead of a file edit they will have to undo later.
