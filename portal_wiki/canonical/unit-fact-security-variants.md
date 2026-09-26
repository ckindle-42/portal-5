---
id: unit-fact-security-variants
kind: what
title: 16 security canonical variants
sources:
- type: code
  path: config/portal.yaml
  commit: 1179539abbf8
  section: workspaces.auto-security.variants
claims: []
confidence: high
tags:
- fact
- security
created_at: 1784000421.308071
updated_at: 1790432976.303871
---

# Security canonical variants (16)

sec-bench `--workspaces` targets, addressed as `auto-security::<variant>`:

- `auto-security::blueteam`
- `auto-security::blueteam-council`
- `auto-security::blueteam-orchestrated`
- `auto-security::bully-handoff-drafter`
- `auto-security::pentest`
- `auto-security::purpleteam`
- `auto-security::purpleteam-deep`
- `auto-security::purpleteam-exec`
- `auto-security::redteam`
- `auto-security::redteam-deep`
- `auto-security::security-council-granite41-30b`
- `auto-security::security-council-mistral-small32-24b`
- `auto-security::security-council-qwen36-27b`
- `auto-security::security-expert-foundation-sec-8b`
- `auto-security::security-tool-granite41-8b`
- `auto-security::uncensored`

## Why

The canonical variant set is the `variants` map on the `auto-security` workspace in `config/portal.yaml`. Each entry is an `auto-security::<variant>` id that `sec-bench --workspaces` targets; the pipeline resolves the variant to a model pool the same way a `?variant=` hint on any workspace does. Deriving the list from config keeps the documented target set and the live routing surface aligned.
