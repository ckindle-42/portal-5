---
id: unit-claude-reconcile-the-stale-docs-against-live-code
kind: why
title: "CLAUDE.md \u2014 ...reconcile the stale docs against live code..."
sources:
- type: design
  path: CLAUDE.md
  section: '...reconcile the stale docs against live code...'
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.1943622
updated_at: 1785348301.1943622
---

python3 scripts/doc_ledger.py stamp <doc>         # or stamp-all after a full pass
```

Enforcement: `scripts/validate_system.py` check **`AK. doc currency`** fails when any bound source changed since a doc's stamp. `bash scripts/ci_local.sh` will be red until docs are reconciled. The re-runnable remediation is `TASK_DOC_AUDIT_AGENT_V*.md` — the doc-side analogue of the validate/test harness.

**Never hardcode counts/ports/check-letters as prose** (persona counts, workspace counts, port tables, validate check letters). Derive them from an extractor at reconcile time; a hardcoded persona count written from memory is drift waiting to happen.
