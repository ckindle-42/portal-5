---
id: unit-sec-core-compliance_report
kind: mixed
title: "Compliance report \u2014 multi-framework mapping"
sources:
- type: code
  path: portal/modules/security/core/compliance_report.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902832
updated_at: 1785800295.902832
---

The compliance-report generator that maps the security findings across the frameworks (NERC CIP, and the others), producing the compliance posture report.

## Why

The report stays in the security module because it is the RBP engine's own compliance generator — a finding needs mapping to the frameworks it implicates, and that mapping is a security-module capability, not the compliance discipline's implementation.

## Interfaces

The compliance-report generator that maps the security findings across the frameworks (NERC CIP, and the others), producing the compliance posture report lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
