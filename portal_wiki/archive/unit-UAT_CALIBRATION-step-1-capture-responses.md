---
id: unit-UAT_CALIBRATION-step-1-capture-responses
kind: why
title: "UAT_CALIBRATION \u2014 Step 1 \u2014 Capture responses"
sources:
- type: design
  path: docs/UAT_CALIBRATION.md
  section: "Step 1 \u2014 Capture responses"
last_generated_commit: ''
confidence: high
tags:
- docs
- UAT_CALIBRATION
created_at: 1783195000.918269
updated_at: 1783195000.918269
---


```bash
python3 tests/portal5_uat_driver.py --calibrate --calibrate-output calibration.json
```

This runs every test once (or a subset with `--section` / `--test`) and saves a JSON file with one record per test:

```json
{
  "test_id": "WS-01",
  "name": "Auto Router — Intent-Driven Routing",
  "section": "auto",
  "workspace": "auto",
  "prompt": "I need to deploy a containerized Python app...",
  "response_text": "Here are the Deployment and Service manifests...",
  "chat_url": "http://localhost:8080/c/abc123",
  "review_tag": "",
  "timestamp": "2026-04-25T14:30:00Z"
}
```

---
