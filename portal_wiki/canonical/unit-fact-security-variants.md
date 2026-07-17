---
id: unit-fact-security-variants
kind: what
title: 9 security canonical variants
sources:
- type: code
  path: config/portal.yaml
  commit: 2459cb972bf0
  section: workspaces.auto-security.variants
last_generated_commit: 2459cb972bf0
confidence: high
tags:
- fact
- security
created_at: 1784000421.308071
updated_at: 1784327242.8022609
---

# Security canonical variants (9)

sec-bench `--workspaces` targets, addressed as `auto-security::<variant>`:

- `auto-security::blueteam`
- `auto-security::blueteam-orchestrated`
- `auto-security::pentest`
- `auto-security::purpleteam`
- `auto-security::purpleteam-deep`
- `auto-security::purpleteam-exec`
- `auto-security::redteam`
- `auto-security::redteam-deep`
- `auto-security::uncensored`
