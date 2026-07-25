---
id: unit-portal5-acceptance-execute-v9-results-dashboard
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Results + dashboard"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: Results + dashboard
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.696529
updated_at: 1784946220.696529
---

```bash
python3 scripts/update_grafana_acceptance.py --input ACCEPTANCE_RESULTS.md
git add ACCEPTANCE_RESULTS.md config/grafana/dashboards/portal5_acceptance.json
git commit -m "acceptance: run <date> — <N> sections, <pass>/<total>, <notable>"
```

---
