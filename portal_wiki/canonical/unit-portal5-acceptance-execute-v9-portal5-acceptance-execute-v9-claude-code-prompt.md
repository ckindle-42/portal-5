---
id: unit-portal5-acceptance-execute-v9-portal5-acceptance-execute-v9-claude-code-prompt
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014\
  \ Claude Code Prompt"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Claude Code Prompt"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6935182
updated_at: 1784946220.6935182
---

> **Supersedes** `PORTAL5_ACCEPTANCE_EXECUTE_V8.md` (archive to
> `docs/_archive_execdocs/`). V9 updates for the post-collapse / post-alias-
> retirement / post-routing-integrity codebase (HEAD `87b19bf`).

**V9 changes from V8:**
- **Workspace count corrected: 21 production workspaces** (V8 said 35 — that was
  pre-collapse). The collapse folded 104→21; counts are config-driven, so the
  preflight prints the live number.
- **Retired-alias S6 references removed.** V8 said "S6 adds auto-redteam-deep/
  auto-pentest/auto-purpleteam/…". Those ids are **retired**; S6 now tests
  `auto-security` with variant awareness (the section code was already migrated
  in the alias-finish work — s06 asserts routing to `auto-security` for
  redteam/blueteam/etc. intents).
- **New:** routing-integrity baseline (`tests/routing/baseline.json`) and
  served-model correctness (`model_pin`) are now assertable — S3/S21 tie into
  the routing regression; S10 personas can be served-model-checked.
- bench-* workspaces remain **out of acceptance scope by design** — full-catalog
  routing + TPS is `bench_tps.py`'s job.

**Scale is config-driven — run the preflight; don't trust baked numbers:**
```bash
python3 scripts/execute_preflight.py     # 21 production workspaces, 138 personas
```

The acceptance suite is not a benchmark and asserts no TPS/perf numbers.

---
