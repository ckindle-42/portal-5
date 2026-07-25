---
id: unit-known-limitations-70b-dense-models-unusable-for-daily-routing-on-m4-pro-64gb
kind: what
title: "KNOWN_LIMITATIONS \u2014 70B Dense Models Unusable for Daily Routing on M4\
  \ Pro 64GB"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: 70B Dense Models Unusable for Daily Routing on M4 Pro 64GB
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.673774
updated_at: 1784946220.673774
---

- **ID**: P5-SPEED-001
- **Description**: Llama-3.3-70B-Instruct-4bit and DeepSeek-R1-Distill-Llama-70B-4bit measure ~3.5 TPS warm — too slow for interactive use. 3-bit quantization (~28GB) is theoretically viable at ~9.7 TPS but not yet bench-validated.
- **Mitigation**: All daily-routed workspaces use ≤33B models. 70B variants are bench-tier only.
