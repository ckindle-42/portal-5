---
id: unit-lab-setup-metadata-only-skip-heavy-vulhub-model-pulls
kind: what
title: "LAB_SETUP \u2014 Metadata-only (skip heavy vulhub + model pulls):"
sources:
- type: code
  path: scripts/lab_setup.py
- type: code
  path: scripts/lab_ready.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.518987
updated_at: 1784946220.518987
---

The metadata-only path is `python3 scripts/lab_setup.py --skip-heavy`. Under
the flag every step in `STEPS` short-circuits before downloading: the vulhub
clone returns skipped with the reason --skip-heavy, the challenges step returns
before materializing any directory, and the models step returns before invoking
`./launch.sh pull-models`. The provisioner therefore prints its plan and exits
having downloaded nothing. This is the safe way to prepare a lab machine when
the heavy vulhub and model downloads must be deferred to a later maintenance
window.

## Why

A --skip-heavy mode exists because the full setup can pull gigabytes across the
clone and model steps, and an operator may want to validate configuration or run
the readiness gate first. Marking the download steps heavy in the `STEPS` table
keeps the decision explicit in one place instead of scattering skip logic
through the script body.
