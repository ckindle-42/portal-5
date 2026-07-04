---
id: unit-UAT_CALIBRATION-step-3-generate-signals
kind: why
title: "UAT_CALIBRATION \u2014 Step 3 \u2014 Generate signals"
sources:
- type: design
  path: docs/UAT_CALIBRATION.md
  section: "Step 3 \u2014 Generate signals"
last_generated_commit: ''
confidence: high
tags:
- docs
- UAT_CALIBRATION
created_at: 1783195000.918765
updated_at: 1783195000.918765
---


```bash
python3 tests/portal5_uat_driver.py \
  --emit-signals-from calibration.json \
  --calibrate-output updated_signals.py
```

This writes `updated_signals.py` containing:

- `CALIBRATION_SIGNALS` dict — top-10 TF-IDF keywords per section
- Suggested `assert_contains` entries for the UAT test catalog

---
