---
id: unit-HOWTO-offensive-security-simulation-auto-redteam-auto-re
historical: true
kind: why
title: "HOWTO \u2014 Offensive Security \u2014 Simulation (auto-redteam / auto-redteam-deep)"
sources:
- type: design
  path: docs/HOWTO.md
  section: "Offensive Security \u2014 Simulation (auto-redteam / auto-redteam-deep)"
confidence: high
tags:
- docs
- HOWTO

---


Red team workspaces generate structured ATT&CK content. **No tools** — simulation only.

1. Select `Portal Red Team` (fast, 9B) or `Portal Red Team · Deep` (SuperGemma4-26B, denser ATT&CK coverage)
2. Type: `Enumerate attack vectors against an Active Directory environment with Kerberos`
3. Output structured with `## ATTACK VECTORS`, `## EXPLOITATION`, `## PERSISTENCE`, `## DEFENDER CUE`

LLM-based intent classifier auto-routes offensive prompts to `auto-security` with the `redteam`
variant selected; keyword scoring provides fallback (signals like "exploit", "payload", "shellcode"
trigger routing).
