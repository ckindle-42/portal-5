---
id: unit-SECURITY_FLEET_REVIEW_2026-06-add-validated-by-run-b-chain-bench
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 Add (validated by Run B chain bench)"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: Add (validated by Run B chain bench)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.915811
updated_at: 1783195000.915811
---


| Model | Fleet Cov | Run B Avg | Run B Depth | TPS | Training purpose | Target role |
|---|---|---|---|---|---|---|
| `lfm2.5:8b` | 1.00 | **1.00** | 11.5 | 78.5 | Agentic tool use, hybrid architecture | `auto-security` — fast, agentic by design, non-transformer architecture diversity. kerberoast depth=14, asrep depth=9 — both WIN at 30s avg. |
| `granite4.1:8b` | 1.00 | **1.00** | 8.0 | 19.3 | Enterprise structured output, compliance | `auto-blueteam` support — structured output + instruction fidelity; right for SPL/KQL, detection engineering. kerberoast depth=8, asrep depth=8 — both WIN at 15s avg (fastest in batch). |
