---
id: unit-claude-new-cluster-node
kind: why
title: "CLAUDE.md \u2014 New Cluster Node"
sources:
- type: design
  path: CLAUDE.md
  section: New Cluster Node
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.1943822
updated_at: 1785348301.1943822
---

1. Edit `config/backends.yaml` — add backend entry, assign to group
2. `docker compose restart portal-pipeline`
3. Done. No code changes.
4. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp

---
