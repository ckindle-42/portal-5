---
id: unit-known-limitations-phi4-reasoning-plus-crashes-ollama-s-llama-server-on-this-host-confirmed-not-a-corrupted-download
kind: what
title: "KNOWN_LIMITATIONS \u2014 phi4-reasoning:plus crashes Ollama's llama-server\
  \ on this host \u2014 CONFIRMED NOT a corrupted download"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "phi4-reasoning:plus crashes Ollama's llama-server on this host \u2014\
    \ CONFIRMED NOT a corrupted download"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.673387
updated_at: 1784946220.673387
---

- **ID**: P5-MODEL-PHI4REASONING-001
- **Description**: Both `phi4-reasoning:plus` and `phi4-reasoning:plus-ctx32k` fail on direct `POST /api/generate` with `{"error":"llama-server process has terminated: signal: abort trap"}` — a local Ollama/model-file issue, not a routing or pipeline bug. Discovered during `DESIGN_PERSONA_INTENT_REMEDIATION_V1.md`'s live verification of the `phi4stemanalyst` persona's `model_pin`: the pipeline correctly resolved and requested `phi4-reasoning:plus-ctx32k` (confirmed in logs — `wanted phi4-reasoning:plus-ctx32k`), the registry's existing backend-failover mechanism correctly caught the crash and fell back to another reasoning-pool model, and honestly logged `model_hint mismatch ... response may be from wrong model` rather than silently misreporting. The routing/pin mechanism is proven correct by the other 4 personas (`magistralstrategist`, `devstral_coder`, `glm-coder`, `glm-thinker`) succeeding cleanly end-to-end.
- **Root cause CONFIRMED (2026-07-13, TASK_MODEL_POOL_REACHABILITY_FIX.md live-confirm)**: `ollama rm phi4-reasoning:plus-ctx32k phi4-reasoning:plus`, full re-pull of `phi4-reasoning:plus` from scratch, and rebuild of both ctx-tagged variants via `ollama create` — crash reproduced identically on the freshly-pulled base model. **Not a corrupted download.** `/opt/homebrew/var/log/ollama.log` shows the abort originates in llama.cpp's device-memory-fitting path (`common_fit_params` → `common_params_fit_impl` → `common_get_device_memory_data_impl`) during model load on Ollama 0.31.1 — a real incompatibility between this GGUF and the installed llama-server build on this host (Apple Silicon Metal backend), not model-file integrity.
- **Impact**: `phi4stemanalyst` currently falls back to whatever `auto-reasoning`'s pool serves instead of Phi-4-reasoning-plus. Given the confirmed crash, the persona has been re-identified generically (no `model_pin`, no Phi-4 branding in tags/comments) rather than left claiming an identity it can't serve — it now intentionally serves `auto-reasoning`'s pool default (`DeepSeek-R1-0528-Qwen3-8B`). `config/backends.yaml`'s `reasoning` backend group intentionally does NOT include `phi4-reasoning:plus-ctx32k` — do not add it without first resolving this crash.
- **Mitigation options not yet tried**: (1) upgrade/downgrade Ollama to a different llama.cpp vendor commit and retest; (2) try a different quantization/source GGUF for Phi-4-reasoning-plus (this one may be built with a `common_fit_params` code path this Ollama build mishandles); (3) file upstream against Ollama/llama.cpp with the log excerpt above. Re-pulling alone will NOT fix it — already tried and reproduced.
