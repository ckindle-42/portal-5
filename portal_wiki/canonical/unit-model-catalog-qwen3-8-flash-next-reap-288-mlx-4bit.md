---
id: unit-model-catalog-qwen3-8-flash-next-reap-288-mlx-4bit
kind: what
title: "MODEL_CATALOG — `Qwen3.8-Flash-Next-REAP-288-MLX-4bit`"
sources:
- type: code
  path: config/backends.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1788825600.0
updated_at: 1788825600.0
---

`Qwen3.8-Flash-Next-REAP-288-MLX-4bit` (`sh0wie/Qwen3.8-Flash-Next-REAP-288-MLX-4bit` on Hugging Face) is a REAP expert-pruned MLX affine 4-bit conversion of `Qwen/Qwen3.8-Flash-Next`. REAP (Router-weighted Expert Activation Pruning, arXiv:2510.13999, Lasby et al., ICLR 2026) drops the MoE from 512 to 288 experts; the base is a 180B-class MoE with ~6B active params/token and top-10 routing. The backbone is quantized at group size 64 and the PLE (per-layer-embedding) n-gram table at group size 32. It was added 2026-09-02 (`TASK_OMLX_QWEN38FN_REAP288_BRINGUP_V1`) as a **bench-only** candidate wired to the `bench-qwen38-flash-next-reap288` workspace in `config/portal.yaml` (`module: eval`, `PROMOTE_POLICY=confirm`). `config/backends.yaml` registers it in the `omlx-coding` entry (group `coding`, `priority: 10`) — the same shadow-shift oMLX serving path `auto-coding` uses, but `auto-coding`'s own `model_hint`/priority/aliases are unchanged. There is no GGUF/Ollama fallback for this checkpoint, so the hint is oMLX-only, the same pattern as the `Qwen3.8-27B-4bit` DFlash2 entry.

The checkpoint requires oMLX >= 0.6.4 **and** `qwen4_ple_ssd_offload: true` in `~/.omlx/model_settings.json` (host config, not in this repo). With that setting oMLX logs `Qwen4-Exp PLE mode: mmap`, keeps the ~32GB PLE n-gram table on SSD, and the loaded footprint is 39.13GB actual resident — matching the model card's "39 GB streamed" and the source plan's ~39GB estimate. oMLX's admission-time estimate is padded higher (40.57GB with the setting, 71.87GB without; `qwen4_exp_residency_estimate.resident_bytes` reports a conservative 77GB), and without the setting oMLX auto-forces the offload only when the memory ceiling is already >= 45GB and otherwise refuses the load with HTTP 507 (`Model (71.87GB) does not fit`). On disk ~70GB (`du -sh`; config `checkpoint_bytes` 73.5GB; card 68GB).

Probed on this host 2026-09-02: the 40.57GB admission estimate does not pass co-resident with the full Portal Docker stack + Ollama (~25GB reclaimable), so the probe ran with the stack down (`./launch.sh down` + Ollama evicted, ~41-53GB reclaimable). First load ~22s; **warm sustained decode ~23-29 tok/s** (256-300 token gens) on this M4 Pro via the streamed-PLE path — in line with the card's ~28 tok/s, which is stock mlx-vlm with the table *resident*; the card explicitly does not separately benchmark oMLX's streamed path. Early 6-11 tok/s readings were a cold-load artifact (tiny gens right after the 22s load), not a settings problem. Levers checked and ruled out: `model_type_override: "llm"` fails ("Model type qwen4_exp not supported" — VLM engine is the only path); no `mtp.*`/draft tensors so no speculative decode; `/Volumes/data01` (PLE-table source) is an external Thunderbolt PCIe SSD at ~3 GB/s sequential, adequate NVMe. It is a thinking model (reasoning in the `reasoning_content` field). `supports_tools: true` — verified via a direct `/v1/chat/completions` tool-call probe: clean `tool_calls` block, `get_weather` with `{"location": "Little Rock, AR"}` correctly typed, `finish_reason: tool_calls`. Card HumanEval 91.5% (vs 93.9% base Q4) not reproduced here.

## Why

Grounding anchors the model to its bench-only oMLX registration and the REAP provenance (512->288 expert pruning of a 180B-class MoE). **Operator verdict 2026-09-02: this must never become an `auto-*` default — too heavy (39GB loaded plus a 40.57GB admission gate that needs a quiet host); bench / restricted manual use only, and only if proven against the Laguna-XS.2 primary.** This is firmer than the bring-up task's original `[GATE]`, which merely deferred the promotion decision. The hard `qwen4_ple_ssd_offload` requirement and the gap between the 39GB loaded footprint and the 40.57GB admission gate (which needs a quiet host) are what a future session needs before attempting a bench; the decode speed and tool-call result are recorded from the quiet-host probe.
