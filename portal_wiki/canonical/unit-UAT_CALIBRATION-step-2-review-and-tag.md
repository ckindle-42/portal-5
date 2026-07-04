---
id: unit-UAT_CALIBRATION-step-2-review-and-tag
kind: why
title: "UAT_CALIBRATION \u2014 Step 2 \u2014 Review and tag"
sources:
- type: design
  path: docs/UAT_CALIBRATION.md
  section: "Step 2 \u2014 Review and tag"
last_generated_commit: ''
confidence: high
tags:
- docs
- UAT_CALIBRATION
created_at: 1783195000.918519
updated_at: 1783195000.918519
---


Open `calibration.json` and set `review_tag` for each entry:

| Tag | Meaning |
|-----|---------|
| `"good"` | Response is correct and representative — use for signal extraction |
| `"bad"` | Response is wrong, incomplete, or refused — do not use |
| `"skip"` | Exclude from signal extraction (neutral / not enough content) |

Leave `review_tag` as `""` to skip an entry silently.

---
