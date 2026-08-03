---
id: unit-security-knowledge-surface
kind: mixed
title: "Security knowledge \u2014 detection grounding re-export boundary"
sources:
- type: code
  path: portal/modules/security/knowledge/__init__.py
  commit: b0aa6770
last_generated_commit: b0aa6770
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- knowledge
created_at: 1785795023.449225
updated_at: 1785795023.449225
---

The knowledge subpackage is the stable re-export boundary over the security
module's detection grounding: the SPL detection library and technique
reference (from `core.siem`), the scenario definitions (`SCENARIOS`), and the
wiki-backed technique-signature seeding (from `portal.platform.wiki`
adapters). The RBP engine stays intact; this package is the one public door
onto its knowledge.

## Why

Other code — and future modules — should depend on this surface instead of
reaching into `core.siem` or `core.exec_chain` internals directly. That
boundary is what lets the detection library be reorganised internally without
breaking its consumers, and it is the same facade pattern the platform
storage package uses for the config loader. The wiki seeding functions are
re-exported here because a technique signature is itself knowledge about the
library, so the seeding belongs to the same knowledge surface rather than
being reached through the wiki adapters.

## Interfaces

`spl_for`, `spl_variants_for`, `technique_reference`,
`technique_signature_full`, and `techniques_covered` cover the SPL library;
`SCENARIOS` the scenario definitions; `seed_dcsync_specifically` and
`seed_technique_signatures` the wiki seeding. All are re-exported through
`__all__` so the surface is explicit.
