---
id: unit-sec-core-oast_bench
kind: mixed
title: "OAST bench \u2014 browser/DOM security + collaborator"
sources:
- type: code
  path: portal/modules/security/core/oast_bench.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394149
updated_at: 1785800269.394149
---

The out-of-band application security test bench, reusing the Playwright MCP for browser/DOM security and a self-hosted OAST collaborator.

## Why

OAST is the technique for detecting blind vulnerabilities — the test induces an out-of-band callback and observes whether it arrives. The bench combines the browser MCP for the DOM side with the self-hosted collaborator for the callback side, which is what detects blind injection without a visible response.

## Interfaces

The out-of-band application security test bench, reusing the Playwright MCP for browser/DOM security and a self-hosted OAST collaborator lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
