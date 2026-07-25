---
id: unit-known-limitations-model-parity-specialist-models-lost-in-the-mlx-ollama-migration
kind: what
title: "KNOWN_LIMITATIONS \u2014 Model Parity \u2014 Specialist models lost in the\
  \ MLX\u2192Ollama migration"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "Model Parity \u2014 Specialist models lost in the MLX\u2192Ollama migration"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.668331
updated_at: 1784946220.668331
---

Two production specialist models were MLX-only safetensor builds with no
verified GGUF equivalent. The migration (3a0c58e) remapped their
workspaces to general-purpose GGUF substitutes:

| Workspace(s) | Original (MLX) | Now served (Ollama GGUF) | Gap |
|---|---|---|---|
| `auto-security` (blueteam variant), `bench-foundation-sec` | Foundation-Sec-8B-Reasoning (Cisco, purpose-trained defender cybersec: CVE→CWE, MITRE ATT&CK, SOC triage) | Foundation-Sec-8B-Reasoning Q8_0 GGUF (Cisco fdtn-ai, first-party, ~8.5GB) | RESTORED (P5-FUT-PARITY-001) |
| `tools-specialist`, `bench-toolace25` | ToolACE-2.5-Llama-3.1-8B (Team-ACE, BFCL-topping tool-caller) | granite4.1:8b (general tool-tagged, BFCL V3 68.27, first-party IBM) | ACCEPTED — granite4.1:8b adopted; ToolACE-2.5 dropped (P5-FUT-PARITY-001 closed) |

**Status — Foundation-Sec:** RESTORED to auto-security's 'blueteam' variant production primary
via the first-party Cisco GGUF `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`
(TASK_PARITY_FOUNDATION_SEC_V1, direct swap, no bench gate — consistent with how
the original MLX→Ollama migration set models by assumption; this restores the
pre-migration primary).

**Status — ToolACE:** RESOLVED (accepted). granite4.1:8b adopted as the
tools-specialist model by operator decision; ToolACE-2.5 evaluated and dropped
(no verified ToolACE-2.5 GGUF confirmed; self-quant + Ollama tool-template risk
not justified). P5-FUT-PARITY-001 is CLOSED/DONE — both specialists dispositioned
(Foundation-Sec restored, ToolACE substitute accepted).

---
