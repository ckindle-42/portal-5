---
id: unit-portal5-bench-execute-v4-3-backends-up
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 3. Backends up?"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: 3. Backends up?
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.7008882
updated_at: 1784946220.7008882
---

curl -s localhost:11434/api/tags  >/dev/null && echo "ollama ok"
curl -s localhost:9099/health     >/dev/null && echo "pipeline ok"
```

**`PORTAL_ENABLE_EVAL=1` is required** — without it the eval/bench workspaces
don't load and the plan is incomplete. The bench harness sets this itself in
its entry point, but set it explicitly for the dry-run so your plan matches the
real run.

If the preflight reports a retired-alias leak, STOP — the surface has regressed
(a retired id like `auto-redteam`/`auto-phi4` reappeared); do not bench a broken
surface.

---
