---
id: unit-claude-12-docs-travel-with-the-work
kind: why
title: "CLAUDE.md \u2014 12 \u2014 Docs Travel With The Work"
sources:
- type: design
  path: CLAUDE.md
  section: "12 \u2014 Docs Travel With The Work"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.194359
updated_at: 1785348301.194359
---


Documentation is coupled to code the same way Rule 6 couples workspaces to `portal.yaml`: **mechanically, and CI-gated.** Every living doc is bound in `docs/.doc_ledger.yaml` to the source paths that determine its correctness, plus the commit it was last reconciled against. A doc is *stale* the moment a bound source changes past that commit.

**The rule:** when your change touches a subsystem, reconcile the docs bound to it **in the same task**, then re-stamp. Do not defer doc updates to "later" — later is how the docs rotted in the first place.

```bash
python3 scripts/doc_ledger.py status              # what drifted
