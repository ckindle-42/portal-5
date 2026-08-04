---
id: unit-sec-core-re_firmware
kind: mixed
title: "Firmware RE \u2014 ported reverse-engineering benches"
sources:
- type: code
  path: portal/modules/security/core/re_firmware.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.39416
updated_at: 1785800269.39416
---

The firmware reverse-engineering benches ported from skill methodologies, each scored on ground truth (emulated firmware, known CVE, config extraction).

## Why

The benches score against ground truth rather than open-ended judgment: emulated firmware with a known CVE and a config-extraction goal. That ground truth is what makes the RE capability measurable rather than a matter of opinion.

## Interfaces

The firmware reverse-engineering benches ported from skill methodologies, each scored on ground truth (emulated firmware, known CVE, config extraction) lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
