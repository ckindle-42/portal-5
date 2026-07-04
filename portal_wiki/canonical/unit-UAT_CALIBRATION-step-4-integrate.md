---
id: unit-UAT_CALIBRATION-step-4-integrate
kind: why
title: "UAT_CALIBRATION \u2014 Step 4 \u2014 Integrate"
sources:
- type: design
  path: docs/UAT_CALIBRATION.md
  section: "Step 4 \u2014 Integrate"
last_generated_commit: ''
confidence: high
tags:
- docs
- UAT_CALIBRATION
created_at: 1783195000.919019
updated_at: 1783195000.919019
---


Review `updated_signals.py`, then:

1. Merge relevant entries into `tests/quality_signals.py` (`QUALITY_SIGNALS` dict)
2. Add suggested `assert_any_of` entries to the matching tests in the catalog generators (`tests/uat_catalog/g_*.py`)
3. Commit both files with a message like:
   ```
   test(uat): update quality signals from calibration-YYYY-MM-DD
   ```

---
