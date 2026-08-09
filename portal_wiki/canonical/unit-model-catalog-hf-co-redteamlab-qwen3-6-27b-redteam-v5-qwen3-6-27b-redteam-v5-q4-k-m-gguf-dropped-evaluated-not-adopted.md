---
id: unit-model-catalog-hf-co-redteamlab-qwen3-6-27b-redteam-v5-qwen3-6-27b-redteam-v5-q4-k-m-gguf-dropped-evaluated-not-adopted
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/RedTeamLab/Qwen3.6-27B-redteam-v5:qwen3.6-27b-redteam-v5-Q4_K_M.gguf`\
  \ \u2014 DROPPED (evaluated, not adopted)"
sources:
- type: code
  path: portal/modules/security/core/candidate_eval.py
- type: code
  path: config/portal.yaml
last_generated_commit: 63cbca4c591d2d00f1cc9e3101ffa91f84a9a4a0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6264472
updated_at: 1784946220.6264472
---

The `candidate_eval.py` harness evaluates a candidate model in a slot against the fleet incumbent and writes a `cand_<model>_<slot>_<ts>.json` verdict to `portal/modules/security/core/results/candidates/`, with `PROMOTE_POLICY=confirm` meaning it reports deltas and never swaps fleet config. The RedTeamLab Qwen3.6-27B redteam-v5 model was run through this exploit-slot gauntlet on 2026-07-03 and the recorded outcome was a neutral-to-slightly-negative aggregate delta against the incumbent — coverage and lab-success flat, order-accuracy dipping, and the chain stopping well short of the incumbent's depth on the `web_sqli_dump` and `ctf_multi_service` scenarios. A comment in `candidate_eval.py` confirms this model's first run was silently lost to a result-file path-sanitization bug and had to be rerun. The model was not adopted: nothing in `config/portal.yaml` or `config/backends.yaml` references the id today.

## Why

The prior body stated a TPS reading and a below-floor intake override that no tracked file records, so those were deleted. What the tracked harness, its path-bug comment, and the configs do establish is the whole comparative outcome: the candidate ran in the exploit slot under `PROMOTE_POLICY=confirm`, the rerun record landed neutral-to-negative on the two web scenarios, the lost-first-run bug is pinned by the harness comment, and the id appears in no live workspace or backend entry — the mechanical basis for the dropped verdict.
