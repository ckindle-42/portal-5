---
id: unit-model-catalog-ravenx-cyberagent-35b-q4-k-m-dropped-evaluated-not-adopted-local-alias-for-ravenx-cyberagent-35b
kind: what
title: "MODEL_CATALOG \u2014 `ravenx-cyberagent-35b:Q4_K_M` \u2014 DROPPED (evaluated,\
  \ not adopted; local alias for RavenX-CyberAgent-35B)"
sources:
- type: code
  path: portal/modules/security/core/candidate_eval.py
- type: code
  path: config/portal.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.625427
updated_at: 1784946220.625427
---

The `candidate_eval.py` harness evaluates a candidate model in a slot against the fleet incumbent and writes a `cand_<model>_<slot>_<ts>.json` verdict to `portal/modules/security/core/results/candidates/`, with `PROMOTE_POLICY=confirm` meaning it reports deltas and never swaps fleet config. The `ravenx-cyberagent-35b:Q4_K_M` candidate (a local alias for RavenX-CyberAgent-35B) was run through this exploit-slot gauntlet on 2026-07-03 and the recorded outcome was a neutral aggregate delta against the incumbent — flat coverage and lab-success with a slight order-accuracy edge, the only real edge being full chain depth on the `web_sqli_dump` scenario. The model was not adopted: nothing in `config/portal.yaml` or `config/backends.yaml` references the id today, so the record stands as a dropped candidate.

## Why

The prior body carried operational lore — a TPS probe reading, an intake-floor override, and an ollama-create workaround for an over-long upstream repo name — that no tracked file records, so those claims were deleted. What the tracked harness and config do establish is the eval itself: the candidate ran in the exploit slot under `PROMOTE_POLICY=confirm`, the outcome landed neutral, and the id appears in no live workspace or backend entry, which is the mechanical basis for calling it a dropped, not adopted, candidate.
