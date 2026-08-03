---
id: unit-uat-calibration
kind: mixed
title: "UAT calibration \u2014 scoring calibration"
sources:
- type: code
  path: tests/uat/calibration.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799319.124385
updated_at: 1785799319.124385
---

The UAT scoring calibration extracted from the driver monolith.

## Why

The calibration logic normalises raw scores into the thresholds the driver reports against, and centralising it means a calibration change applies to every section uniformly rather than being re-derived per section.

## Interfaces

The calibration functions.

## Gotchas

Extracted verbatim — a change here alters how every section's scores are interpreted.
