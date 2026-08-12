---
id: unit-known-limitations-model-parity-specialist-models-lost-in-the-mlx-ollama-migration
kind: what
title: "KNOWN_LIMITATIONS \u2014 Model Parity \u2014 Specialist models lost in the\
  \ MLX\u2192Ollama migration"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: a23f47b3e687df1693600eeea5b4f3f381b9da20
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.668331
updated_at: 1784946220.668331
---

Two production specialist models were MLX-only safetensor builds with no
verified GGUF equivalent at migration time. The migration (3a0c58e) remapped
their workspaces to GGUF substitutes:

| Workspace(s) | Original (MLX) | Now served (Ollama GGUF) | Gap |
|---|---|---|---|
| `auto-security` (blueteam variant), `bench-foundation-sec` | Foundation-Sec-8B-Reasoning (Cisco, purpose-trained defender cybersec: CVE→CWE, MITRE ATT&CK, SOC triage) | First-party GGUF `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` (in `config/backends.yaml`) | RESTORED via first-party GGUF (P5-FUT-PARITY-001) |
| `tools-specialist`, `bench-toolace25` | ToolACE-2.5-Llama-3.1-8B (Team-ACE, BFCL-topping tool-caller) | granite4.1:8b (general tool-tagged, BFCL V3 68.27, first-party IBM) | ACCEPTED — granite4.1:8b adopted; ToolACE-2.5 dropped (P5-FUT-PARITY-001 closed) |

**Status — Foundation-Sec:** The first-party GGUF is registered in `config/backends.yaml` under the security group. In `config/portal.yaml` it is wired as the `expert_model` of the `blueteam-orchestrated` and `blueteam-council` variants and as the `bench-foundation-sec-8b-reasoning` workspace `model_hint`. The `blueteam` variant's production `model_hint` is `granite4.1:8b-ctx8k`; Foundation-Sec serves the orchestrated/council blue lanes rather than the default blue single-model path.

**Status — ToolACE:** RESOLVED (accepted). granite4.1:8b adopted as the
`tools-specialist` model by operator decision; ToolACE-2.5 evaluated and dropped
(no verified ToolACE-2.5 GGUF confirmed; self-quant + Ollama tool-template risk
not justified). P5-FUT-PARITY-001 is CLOSED/DONE — both specialists dispositioned
(Foundation-Sec restored, ToolACE substitute accepted).

## Why

The MLX-to-Ollama migration could not keep every specialist model because some existed only as MLX safetensors. Re-grounding the two dispositions to the current config shows where each landed: Foundation-Sec returned through a first-party GGUF but now occupies the expert/orchestrated role, not the default blue primary, while ToolACE's slot is deliberately served by a different, tool-tagged model. That mapping is what an operator needs to avoid re-proposing the dropped model.
