---
id: unit-SECURITY_FLEET_REVIEW_2026-06-1-workspace-intent-map
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 1. Workspace Intent Map"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: 1. Workspace Intent Map
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.914433
updated_at: 1783195000.914433
---


| Workspace | Groups pulled | Intent |
|---|---|---|
| `auto-pentest` | security only | Agentic offensive — multi-hop tool-chain execution |
| `auto-redteam` | security + general | Creative adversarial — novel attack paths, lateral thinking |
| `auto-redteam-deep` | security + general | Longer horizon, complex multi-pivot scenarios; latency acceptable |
| `auto-security` | security + general | Vulnerability analysis, threat modeling, security advice — domain knowledge matters more than chain mechanics |
| `auto-security-uncensored` | security + general | Same, no safety filters |
| `auto-blueteam` | **reasoning** + security + general | SOC triage, DFIR, ATT&CK mapping, detection engineering, SPL/KQL writing |
| `auto-purpleteam` | security + general | Attack synthesis mapped to detection response |
| `auto-purpleteam-deep` | security + **coding** + general | Purple + scripting exploits and detections; coding group matters |
| `auto-purpleteam-exec` | security + coding + general | Executive synthesis — attack surface to business risk narrative |

**Important**: `auto-blueteam` pulls from reasoning first, so deepseek-r1 and Foundation-Sec (once moved) are already available there. A model that scores 0 on offensive tool-chains may still be exactly right — just through the reasoning pathway.

---
