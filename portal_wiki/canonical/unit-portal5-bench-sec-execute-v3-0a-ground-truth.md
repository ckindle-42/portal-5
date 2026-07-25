---
id: unit-portal5-bench-sec-execute-v3-0a-ground-truth
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 0a. Ground truth"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: 0a. Ground truth
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.7053828
updated_at: 1784946220.7053828
---

```bash
python3 scripts/execute_preflight.py     # lists live auto-security::* variants; must end "OK to run"
```
Use the printed "Security canonical variants" list as your `--workspaces`
targets. If a variant you expect is missing, confirm against
`config/portal.yaml` `workspaces.auto-security.variants` before assuming a bug.
