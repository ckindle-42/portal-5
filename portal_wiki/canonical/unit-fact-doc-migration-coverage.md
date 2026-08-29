---
id: unit-fact-doc-migration-coverage
kind: what
title: 0/23 docs migrated (0.0%)
sources:
- type: code
  path: portal/platform/wiki/render.py
  commit: c73d5ca76df0
  section: render_report
claims: []
confidence: high
tags:
- fact
- wiki
- migration
created_at: 1784941448.187764
updated_at: 1787961447.113216
---

# Doc migration coverage (0/23 docs migrated, 0.0%)

Total generated blocks across migrated docs: 12

## Migrated docs (content-hash gate only)


## Unmigrated docs

- `README.md`
- `P5_ROADMAP.md`
- `KNOWN_ISSUES.md`
- `KNOWN_LIMITATIONS.md`
- `docs/HOWTO.md`
- `docs/ADMIN_GUIDE.md`
- `docs/SECURITY_BENCH_EXEC.md`
- `docs/USER_GUIDE.md`
- `docs/CLUSTER_SCALE.md`
- `docs/ALERTS.md`
- `docs/PERFORMANCE.md`
- `docs/MCP_DEV_TOOLING.md`
- `docs/COMPLIANCE_FALLBACK_POLICY.md`
- `docs/BACKUP_RESTORE.md`
- `docs/LAB_SETUP.md`
- `docs/PERSONA_MATRIX_CI.md`
- `docs/AGENT_LOOP.md`
- `docs/DESIGN_WIKI_GENERATION_LOOP_V1.md`
- `docs/security/corpus_injection.md`
- `config/MODEL_CATALOG.md`
- `tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md`
- `tests/PORTAL5_BENCH_EXECUTE_V4.md`
- `tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md`

## Why

The migration numbers come from `render_report()` in `portal/platform/wiki/render.py`, which classifies every Tier-1 doc as migrated, unmigrated, or gamed and counts the generated blocks. Deriving the coverage figure from that same function keeps the documented migration state and the one the renderer actually computes identical.
