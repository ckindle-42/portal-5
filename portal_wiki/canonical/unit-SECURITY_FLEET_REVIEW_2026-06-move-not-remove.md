---
id: unit-SECURITY_FLEET_REVIEW_2026-06-move-not-remove
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 Move (not remove)"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: Move (not remove)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.915287
updated_at: 1783195000.915287
---


| Model | From | To | Reason |
|---|---|---|---|
| `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` | security | reasoning | Run A confirmed 400 error on every tool probe — cannot use tool manifests at all. But quality 1.0 in TPS bench and trained for security reasoning. Belongs in reasoning group where it contributes to `auto-blueteam` analytical work: ATT&CK analysis, threat modeling, DFIR reasoning. This is correct placement for its training, not a demotion. |
