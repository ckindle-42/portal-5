---
id: unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps
kind: what
title: "KNOWN_LIMITATIONS — Wan 2.2 fp8_scaled Checkpoints Crash on Apple Silicon MPS (Video Generation Shelved)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 15488af2
  section: Wan 2.2 fp8_scaled Checkpoints Crash on Apple Silicon MPS (Video Generation Shelved)
last_generated_commit: 15488af2
confidence: high
tags:
- docs
created_at: 1785292615.0
updated_at: 1785292615.0
---

- **Description**: Every Wan 2.2 ComfyUI checkpoint published as `*_fp8_scaled.safetensors` (Comfy-Org/Wan_2.2_ComfyUI_Repackaged) crashes at inference time on this host's Apple Silicon MPS + PyTorch 2.13 + comfy_kitchen stack with `RuntimeError: Undefined type Float8_e4m3fn`, thrown from `comfy_kitchen/backends/eager/quantization.py`'s `dequantize_per_tensor_fp8` when it calls `.to(dtype=torch.float8_e4m3fn)`. Confirmed live 2026-07-29 against both `wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors` / `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors` (T2V-A14B) and `wan2.2_s2v_14B_fp8_scaled.safetensors` (S2V-14B), each with all three `UNETLoader` `weight_dtype` options (`default`, `fp8_e4m3fn`, `fp8_e4m3fn_fast`) — same failure every time, ~5-16s into execution (model-load/first-linear-layer, not deep into sampling). `wan2.2_ti2v_5B_fp16.safetensors` (TI2V-5B) is unaffected because it is full fp16, not fp8-quantized — it generated successfully end to end (`portal_ti2v__00001_.mp4`, verified valid H.264/1024x576/8fps/5.125s).
- **Impact**: T2V-A14B and S2V-14B are unusable on this hardware via their `_fp8_scaled` checkpoints. The only working alternative is full fp16/bf16 (`wan2.2_t2v_{high,low}_noise_14B_fp16.safetensors` ~28.6GB each, `wan2.2_s2v_14B_bf16.safetensors` ~32.6GB — roughly 90GB combined, against this project's usual quantized-only model policy; this is a genuine hardware blocker rather than a quality tradeoff, but was not pursued — see Decision below). `video_mcp.py`'s `_WAN22_T2V_A14B_WORKFLOW` was also independently found to be architecturally wrong before this — it assumed a single merged checkpoint file that never existed in any maintained repo; fixed to the real two-expert MoE graph (two `UNETLoader` + two chained `KSamplerAdvanced`, node IDs matching ComfyUI's official `text_to_video_wan22_14B.json` reference workflow) in the same session, independent of the fp8 finding.
- **Decision (2026-07-29)**: Video generation is shelved for this project — Portal 5 will only operate ComfyUI **image** generation (flux/sdxl via `mcp-comfyui`), not video (`mcp-video`). The `mcp-video` container was stopped (`docker compose stop mcp-video`); it is not part of the default `./launch.sh up` set (already `profiles: [comfyui]` gated) and will not be restarted as part of normal operation. The video workflow code (TI2V-5B working, T2V-A14B workflow now architecturally correct but fp8-blocked, S2V-14B same fp8 block, Animate-14B stubbed) is left in place — designed, not deleted — in case Ollama/PyTorch/comfy_kitchen MPS support for fp8 improves later, but nothing video-related should be treated as in operation.
- **Mitigation**: None pursued. If video generation is revisited: (1) check whether a newer PyTorch/comfy_kitchen release fixes MPS float8_e4m3fn support before re-attempting fp8_scaled checkpoints, (2) if not, the fp16/bf16 download is the fallback, sized above.
- **Cleanup (2026-07-29)**: The confirmed-broken `_fp8_scaled` files (`wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors`, `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors`, `wan2.2_s2v_14B_fp8_scaled.safetensors`, plus the S2V-only `wav2vec2_large_english_fp16.safetensors` audio encoder) were deleted from `~/ComfyUI/models/` to reclaim ~42GB — dead weight with no path to working given the shelving decision. `wan2.2_ti2v_5B_fp16.safetensors` (works) and the shared `wan2.2_vae.safetensors`/`umt5_xxl_fp8_e4m3fn_scaled.safetensors` (also used by working TI2V-5B, so proven fine — the crash is specific to the diffusion-model UNETLoader path, not every fp8-named file) were kept.
