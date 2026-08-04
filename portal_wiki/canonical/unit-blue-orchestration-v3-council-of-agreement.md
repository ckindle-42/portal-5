---
id: unit-blue-orchestration-v3-council-of-agreement
kind: why
title: "Roadmap: Council of Agreement \u2014 multi-model cross-checking loop for blue\
  \ orchestration"
sources:
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
- type: code
  path: portal/modules/security/core/council_agreement.py
- type: code
  path: portal/platform/inference/router/council.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- blue-orchestration-v2
- blue-team
- council-of-agreement
- multi-model
- roadmap
- security
- verified-v1
created_at: 1784384260.0117
updated_at: 1784384260.0117
---

# Council of Agreement — multi-model cross-checking loop for blue orchestration

Roadmap item (GATE-D ablation Part II-A) that is now implemented in the
security blue-orchestration core.

## What

`_run_council()` in `portal/modules/security/core/blue_orchestrate.py` is
the council loop: the roster's first reasoning model acts as lead
investigator over the shared tool-and-Hunter evidence hand-off (the same
`capture_expert_handoff` path the ablation measured, I7 additive-only),
then every council member independently concludes from that identical
evidence. The deterministic consensus is `compute_agreement()` /
`AgreementResult` in `portal/modules/security/core/council_agreement.py`,
which translates each member's section output into SUPPORT / REJECT /
ABSTAIN and delegates the quorum and participation math to the platform
council primitive `aggregate_opinions()` in
`portal/platform/inference/router/council.py`. A no-quorum split can be
broken by an optional fed arbiter; a shared signal no technique reaches
quorum routes to `ANOMALOUS_UNCLASSIFIED` (disagreement-as-novelty, I8).

## Activation

`_run_orchestration` invokes the council only when the configured roster
has a `tool` member plus more than one reasoning member — the single-model
3-section path stays untouched otherwise. A standing `_COUNCIL_UNFIT_MODELS`
list warns (never evicts) when a known unfit model is on the roster.

## Why

The council answers the specific question the ablation's HANDOFF_LOSS
finding raised: whether independent models agree on a verdict given
identical evidence, as opposed to whether different models would have
gathered different evidence in the first place. Reusing
`capture_expert_handoff` for the lead-hunter phase means the council
measures agreement, not a parallel reimplementation of the hunter loop,
and delegating quorum math to the shared router council keeps the
security adapter a thin verdict translator instead of a second voting
implementation.
