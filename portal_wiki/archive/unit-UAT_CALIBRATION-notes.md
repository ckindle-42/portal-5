---
id: unit-UAT_CALIBRATION-notes
kind: why
title: "UAT_CALIBRATION \u2014 Notes"
sources:
- type: design
  path: docs/UAT_CALIBRATION.md
  section: Notes
last_generated_commit: ''
confidence: high
tags:
- docs
- UAT_CALIBRATION
created_at: 1783195000.919263
updated_at: 1783195000.919263
---


- Re-run calibration whenever prompts change significantly.
- The IDF weighting reduces generic words (e.g. "response", "model") and surfaces domain-specific terms.
- Use `--section <name>` to calibrate a single section without running the full suite.
