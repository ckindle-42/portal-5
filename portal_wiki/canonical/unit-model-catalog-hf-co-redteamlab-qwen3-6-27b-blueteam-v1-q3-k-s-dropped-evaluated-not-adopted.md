---
id: unit-model-catalog-hf-co-redteamlab-qwen3-6-27b-blueteam-v1-q3-k-s-dropped-evaluated-not-adopted
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/RedTeamLab/Qwen3.6-27B-blueteam-v1:Q3_K_S` \u2014\
  \ DROPPED (evaluated, not adopted)"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.62447
updated_at: 1784946220.62447
---

The blue-defender candidate `hf.co/RedTeamLab/Qwen3.6-27B-blueteam-v1:Q3_K_S` was evaluated and dropped: it is absent from `config/backends.yaml`, and its incumbent `sylink/sylink:8b` is what the config actually carries. `sylink/sylink:8b` sits in the `security` group with `supports_tools: false`, is bound to the `bench-sylink-8b` and `bench-sylink` bench `model_hint`s, and was retired from offensive workspaces before promotion to the auto-blueteam primary. The dropped candidate passed preflight and tool-call audit but purple-benched at zero detections on every gauntlet scenario against the fixed red model, exactly matching the incumbent's zero-detection result with no improvement.

## Why

The absent-from-registry fact is the decisive grounding: `config/backends.yaml` never lists the RedTeamLab id, while the incumbent it was compared against, `sylink/sylink:8b`, is verifiably present under `security` with `supports_tools: false`. `config/portal.yaml` confirms the incumbent's bench and blueteam roles. The evaluation outcome is preserved because it is the reason the candidate was never adopted, and it explains the `supports_tools: false` limitation the incumbent carries.
