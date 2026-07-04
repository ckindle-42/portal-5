---
id: unit-SECURITY_FLEET_REVIEW_2026-06-7-role-corrections-summary
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 7. Role Corrections Summary"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: 7. Role Corrections Summary
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.917693
updated_at: 1783195000.917693
---


The fleet bench was read correctly for scores, but training purpose was not factored into placements. Two corrections beyond just adding/removing:

1. **SYLink → blueteam anchor, not redteam-deep**. Training is defensive (SOC, ATT&CK, IR). Its chain depth of 12 reflects SOC investigation multi-step patterns, not offensive TTPs. Correctly kept in security group but its primary workspace contribution should be `auto-blueteam`, not `auto-redteam-deep`.

2. **BaronLLM-abliterated → reinstate as auto-security primary**. Was primary before template issues. 53K domain examples is the deepest security-specific training in the group. Run A: 1.00/1.00 at 11s. Should lead `auto-security`.

3. **Foundation-Sec → reasoning group, not removal**. It reasons about security extremely well. Wrong format (thinking-mode, no tool_calls), wrong group (security agentic). Right domain knowledge for `auto-blueteam` analytical work.

4. **devstral-small-2 → security cross-list for deep workspaces only**. Not a security model. But agentic coding discipline maps to structured chain execution. Useful for `auto-purpleteam-deep` and `auto-redteam-deep` where its 15 TPS and depth 11 are assets.
