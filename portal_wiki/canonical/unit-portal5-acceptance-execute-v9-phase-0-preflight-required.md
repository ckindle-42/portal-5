---
id: unit-portal5-acceptance-execute-v9-phase-0-preflight-required
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Phase 0 \u2014 Preflight (required)"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: "Phase 0 \u2014 Preflight (required)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.694308
updated_at: 1784946220.694308
---

```bash
python3 scripts/execute_preflight.py                 # must end "OK to run"
ps aux | grep portal5_acceptance | grep -v grep      # nothing already running
curl -s localhost:9099/health >/dev/null && echo "pipeline ok"
```

`PORTAL_ENABLE_EVAL` should be **unset** for acceptance — the suite covers the
21 production workspaces, not the eval/bench set. If the preflight shows a
retired-alias leak, STOP (surface regression).

---
