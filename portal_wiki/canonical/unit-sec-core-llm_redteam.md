---
id: unit-sec-core-llm_redteam
kind: mixed
title: "LLM redteam \u2014 OWASP LLM Top 10 probes"
sources:
- type: code
  path: portal/modules/security/core/llm_redteam.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394166
updated_at: 1785800269.394166
---

Probes Portal's own workspaces and MCP surface for OWASP LLM Top 10 vulnerabilities by sending real probes through the pipeline and checking refusal and compliance.

## Why

An LLM platform should be its own red team's first target: the probes exercise the actual pipeline against the OWASP LLM Top 10, and the refusal/compliance checks are what a vulnerable model fails — a model that answers an injection instead of refusing is the finding.

## Interfaces

Probes Portal's own workspaces and MCP surface for OWASP LLM Top 10 vulnerabilities by sending real probes through the pipeline and checking refusal and compliance lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
