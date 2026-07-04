---
id: unit-SECURITY_BENCH_CHAIN_ANALYSIS-pipeline-theory-averages
kind: why
title: "SECURITY_BENCH_CHAIN_ANALYSIS \u2014 Pipeline theory averages"
sources:
- type: design
  path: docs/SECURITY_BENCH_CHAIN_ANALYSIS.md
  section: Pipeline theory averages
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_CHAIN_ANALYSIS
created_at: 1783195000.890953
updated_at: 1783195000.890953
---


| Workspace | Avg theory score | Range |
|---|---|---|
| auto-purpleteam-exec | **0.921** | 0.68 (rbcd) – 1.00 (linux/smb/pth/log4shell) |
| auto-pentest | 0.459 | 0.19 (rbcd) – 0.70 (kerberoasting) |

Pentest pipeline scores are low because the workspace model (general-purpose) doesn't add ATT&CK IDs or section headers — that's a theory-quality limitation of the workspace, not model failure.

---
