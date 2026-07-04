---
id: unit-COMPLIANCE_FALLBACK_POLICY-out-of-scope
kind: why
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Out of scope"
sources:
- type: design
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  section: Out of scope
last_generated_commit: ''
confidence: high
tags:
- docs
- COMPLIANCE_FALLBACK_POLICY
created_at: 1783195000.834145
updated_at: 1783195000.834145
---


This policy covers only `auto-compliance`. Other workspaces with
multi-model fallback chains (`auto-coding`, `auto-research`, `auto-data`,
`auto-security`, etc.) are valid future targets for the same per-backend
matrix approach but require their own scenario fixtures and threshold
documents. The matrix driver is workspace-parameterizable; only the
fixture and threshold doc are workspace-specific.
