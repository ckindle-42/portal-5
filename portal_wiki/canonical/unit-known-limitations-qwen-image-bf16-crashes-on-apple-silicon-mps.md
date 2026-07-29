---
id: unit-known-limitations-qwen-image-bf16-crashes-on-apple-silicon-mps
kind: what
title: "KNOWN_LIMITATIONS — Qwen-Image Apple Silicon Memory and Dtype Constraints"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 1396e41b
  section: Qwen-Image Is Memory-Safe But Produces Black Output on This Apple Silicon MPS Host
last_generated_commit: 1396e41b
confidence: high
tags:
- docs
created_at: 1785294000.0
updated_at: 1785305652.0
---

- **Memory constraint**: The original Qwen-Image-2512 bf16 diffusion and text-encoder pair needs about 57.4GB of static weights. On this 64GB unified-memory host, Docker and loaded Ollama models can leave far less free memory than the nominal capacity. The first unguarded load exhausted host memory and rebooted the machine.
- **Memory-safe configuration**: `qwen-image-2512` uses `qwen_image_fp8_e4m3fn.safetensors` plus `qwen_2.5_vl_7b_fp8_scaled.safetensors`. Admission estimates are 38GB for the base model and 39GB for Lightning. The duplicate estimates in `_admission.py` and the media-memory wiki fact are protected by a unit test.
- **Black-output root cause and fix**: ComfyUI was launched globally with `--force-fp16`. QwenImage declares only bf16 and float32 as supported inference dtypes, but the global override bypassed that selection. A diagnostic `SaveLatent` showed 16,384/16,384 NaNs before VAE decode, proving that the VAE was not the source of the black image. Removing `--force-fp16` from the generated launcher, launchd plist, and current host launcher restored bf16 compute; the same diagnostic then contained no NaNs.
- **Verification**: A 256×256 base diagnostic produced finite latents and a non-degenerate image. A 512×512 Lightning generation produced a detailed fox-astronaut poster with correctly rendered `PORTAL FIVE` text and full-range RGB output. The required 1024×1024, 20-step base-model proof also completed with a prompt-matching non-degenerate image.
- **Why the isolated VAE test failed**: `EmptySD3LatentImage` alone supplies a four-dimensional latent, while Qwen's WanVAE decode path expects the five-dimensional latent produced by the complete Qwen sampling graph. That shape error does not implicate VAE decode in the black-output failure.
- **Remaining limitation — Qwen-Image-Edit-2511**: The bf16 edit checkpoint is estimated at 60GB, and admission control correctly refuses it even with all ComfyUI models unloaded (53.5GB was the best observed free memory, versus 64GB required with headroom). The two official 20.5GB alternatives are not usable on this MPS stack: `fp8mixed` fails comfy-kitchen dequantization with `Undefined type Float8_e4m3fn`; `int8_convrot` requires CPU fallback for unsupported MPS `aten::_int_mm` and did not complete one 512×512 step after more than three minutes. Keep the bf16 refusal and resume from `TASK_QWEN_IMAGE_EDIT_MPS_VARIANT_V1.md`; the next preferred capability fallback is the official 2509 plain-fp8 edit checkpoint.
- **Launcher invariant**: Do not use a global ComfyUI inference-dtype override. Model families declare different supported compute dtypes, and a global fp16 flag can turn an otherwise safe quantized checkpoint into numerically invalid compute.
