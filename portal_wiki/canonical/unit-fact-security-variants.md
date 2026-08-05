---
id: unit-fact-security-variants
kind: what
title: 10 security canonical variants
sources:
- type: code
  path: config/portal.yaml
  commit: db75e444cdca521f9be63059be9180bb380a4a64
  section: workspaces.auto-security.variants
last_generated_commit: db75e444cdca521f9be63059be9180bb380a4a64
claims: []
confidence: high
tags:
- fact
- security
created_at: 1784000421.308071
updated_at: 1785829024.435267
---

# Security canonical variants (10)

sec-bench `--workspaces` targets, addressed as `auto-security::<variant>`:

- `auto-security::blueteam`
- `auto-security::blueteam-council`
- `auto-security::blueteam-orchestrated`
- `auto-security::pentest`
- `auto-security::purpleteam`
- `auto-security::purpleteam-deep`
- `auto-security::purpleteam-exec`
- `auto-security::redteam`
- `auto-security::redteam-deep`
- `auto-security::uncensored`

## Why

The canonical variant set is the `variants` map on the `auto-security` workspace in `config/portal.yaml`. Each entry is an `auto-security::<variant>` id that `sec-bench --workspaces` targets; the pipeline resolves the variant to a model pool the same way a `?variant=` hint on any workspace does. Deriving the list from config keeps the documented target set and the live routing surface aligned.
