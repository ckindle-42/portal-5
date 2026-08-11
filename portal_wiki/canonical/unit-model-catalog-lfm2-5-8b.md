---
id: unit-model-catalog-lfm2-5-8b
kind: what
title: "MODEL_CATALOG \u2014 `lfm2.5:8b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: d19bcd41d50c690918807eab095f1f738f9798d5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6207669
updated_at: 1784946220.6207669
---

`lfm2.5:8b` is Liquid AI's LFM2.5-8B-A1B (~5GB Q4, Apache 2.0), the only non-transformer model in the fleet — a hybrid of gated short convolutions and GQA rather than a pure attention stack. `config/backends.yaml` registers it in `group: general` and `group: security`, both with `supports_tools: true`, which is the cross-listing that gives the security lane a tool-capable generalist. `config/portal.yaml` pins it as the `bench-lfm25-8b` `model_hint` and cites the family in the auto-music description. The 2026-06-20 fleet bench scored it 1.00/1.00 on both scenarios at depth 10 with 78.5 TPS and general quality 1.0.

## Why

This unit moves the LFM2.5 registration claim from doc prose to the two backends.yaml groups that actually list the id and to the bench workspace that consumes it. The supports_tools flag is verified true on both groups, and the auto-music description ties the same family to the music lane, which is the cross-listing fact worth preserving.
