---
id: unit-module-security-redteam
kind: mixed
title: "Security Redteam Module — offensive-generation variants (off by default)"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: portal/platform/inference/config.py
claims:
- probe: modules.disabled
  contains: security_redteam
confidence: high
tags:
- security
- module
- routing
---

# Security Redteam Module — offensive-generation variants (off by default)

`security_redteam` carries the offensive-generation variants of
`auto-security` and nothing else: `redteam`, `redteam-deep` and
`purpleteam-exec`. It is a variant-scoped module in the C7 sense — a variant
declares its own `module:` and a disabled module removes only that variant,
leaving the engine and its other variants served.

## Why it is split out

Red's job in this platform was generating blue training data for the lab.
That is campaign-scoped work, not everyday traffic, and it is the half that
trips frontier-model safety classifiers when an agent reads or edits it. The
split lets the everyday system ship without the offensive-generation surface
while the defensive half stays on, and without deleting a capability the lab
may need again.

## What stays enabled

The defensive and mixed variants keep the `security` module: `blueteam`,
`blueteam-orchestrated`, `blueteam-council`, the security councils,
`security-tool-granite41-8b`, `security-expert-foundation-sec-8b`,
`bully-handoff-drafter`, `pentest`, `uncensored`, and `purpleteam` /
`purpleteam-deep` — the last two carry a red hop but are the
attack-plus-detection output the lane exists for.

## Not a routing change

This module governs which variants are *served*. Whether the auto-router may
*select* the security lane at all is a separate, declarative question
answered by `router: false` on the workspace — see
[[unit-routing-security-operator-selected]]. The red keyword vocabulary stays
in the router's hand-off detector either way: it recognises security work in
order to decline it, and removing it would send such requests back to
scattering into general lanes.

## Module State

The switch is `modules.security_redteam.enabled` in `config/portal.yaml`
(`portal module enable|disable` writes it). Enable it for a generation run,
disable it after. A persona pointing at a variant of a disabled module is not
seeded (`openwebui_init._persona_skips_disabled_variant`), which is why
`pentester` and `redteamoperator` drop out with the variants they drive.
