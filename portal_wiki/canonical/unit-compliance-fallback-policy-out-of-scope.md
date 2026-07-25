---
id: unit-compliance-fallback-policy-out-of-scope
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Out of scope"
sources:
- type: doc
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  commit: 05e42ec2
  section: Out of scope
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.566437
updated_at: 1784946220.566437
---

This policy covers only `auto-compliance`. Other workspaces with
multi-model fallback chains (`auto-coding`, `auto-research`, `auto-data`,
`auto-security`, etc.) are valid future targets for the same per-backend
matrix approach but require their own scenario fixtures and threshold
documents. The matrix driver is workspace-parameterizable; only the
fixture and threshold doc are workspace-specific.
