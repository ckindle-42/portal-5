---
id: unit-LAB_REACHABILITY_DIAGNOSTIC_2026-06-30-gate-behavior-step-4a-4b
kind: why
title: "LAB_REACHABILITY_DIAGNOSTIC_2026-06-30 \u2014 Gate behavior (step 4a/4b)"
sources:
- type: design
  path: docs/LAB_REACHABILITY_DIAGNOSTIC_2026-06-30.md
  section: Gate behavior (step 4a/4b)
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_REACHABILITY_DIAGNOSTIC_2026-06-30
created_at: 1783195000.866705
updated_at: 1783195000.866705
---


| Step | Command | Result |
|---|---|---|
| 4a | `--probe-lab --dry-run` | Passed (dry-run always passes gate) |
| 4b | `--probe-lab --lab-exec --chain-models VulnLLM-R-7B --scenario kerberoast_to_da --dry-run` | Passed (dry-run gate skips) |
| 4b | Same, without `--dry-run` | **Gate aborted**: DC (10.10.11.21) → UNREACHABLE, SRV (10.10.11.33) → UNREACHABLE |

The gate works as designed — it correctly detected both lab targets unreachable and prevented the bench from silently producing another 0/24 result.

---
