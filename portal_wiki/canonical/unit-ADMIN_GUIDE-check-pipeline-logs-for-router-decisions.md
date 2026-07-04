---
id: unit-ADMIN_GUIDE-check-pipeline-logs-for-router-decisions
kind: why
title: "ADMIN_GUIDE \u2014 Check pipeline logs for router decisions"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Check pipeline logs for router decisions
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.8175411
updated_at: 1783195000.8175411
---

./launch.sh logs | grep -E "LLM router|Routing workspace|keyword fallback" | tail -20
