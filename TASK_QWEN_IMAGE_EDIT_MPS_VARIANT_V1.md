# TASK: Make Qwen Image Editing Usable on Apple Silicon MPS

**Task ID:** TASK-QWEN-IMAGE-EDIT-MPS-VARIANT-001
**Priority:** Normal
**Category:** Media capability / platform compatibility
**Status:** Completed 2026-07-29

---

## Goal

Provide a memory-safe, numerically valid Qwen image-editing model on this 64GB
Apple Silicon host without bypassing admission control or globally forcing an
unsupported compute dtype.

## Confirmed safe state

- `qwen-image-edit-2511` still defaults to
  `qwen_image_edit_2511_bf16.safetensors`.
- Its admission estimate remains 60GB plus 4GB headroom. With all ComfyUI
  models unloaded, the host exposed only 53.5GB free, so refusal is valid even
  under the best observed local conditions.
- ComfyUI is running normally without `--force-fp16` and without
  `PYTORCH_ENABLE_MPS_FALLBACK`.
- Do not lower the bf16 estimate or change the default until a replacement
  produces a real edited image.

## Smaller 2511 checkpoints already tested

Both official artifacts were tested and were removed on 2026-07-29 after the
2509 fallback passed. They can be restored from the recorded source if MPS
support changes:

1. `qwen_image_edit_2511_fp8mixed.safetensors` (~20.5GB)
   - Source:
     `Comfy-Org/Qwen-Image-Edit_ComfyUI/split_files/diffusion_models/`
   - Loads safely, but the first sampling call fails in comfy-kitchen 0.2.19:
     `RuntimeError: Undefined type Float8_e4m3fn`.
   - This is the known scaled/mixed fp8 dequantization incompatibility on MPS,
     not a memory failure.
   - ComfyUI prompt ID:
     `8614aa37-66b3-4dcd-b351-157789b83826`.

2. `qwen_image_edit_2511_int8_convrot.safetensors` (~20.5GB)
   - Without fallback, the first sampling call fails because
     `aten::_int_mm` is not implemented for MPS.
   - With `PYTORCH_ENABLE_MPS_FALLBACK=1`, the model loads with 19.5GB resident
     and leaves about 34GB free, but a 512×512 four-step job did not complete
     its first step after more than three minutes. The job was intentionally
     aborted and the global fallback was removed.
   - Error prompt ID:
     `47458d03-3e5a-4f27-8ed1-74d84939bf19`.
   - Slow fallback prompt ID:
     `e90046a6-d4ff-4f22-8db4-53a430db50f3`.

The edit source used by those probes is
`~/ComfyUI/input/qwen_edit_source.png`.

## Recommended next attempts

1. **Test the official 2509 plain-fp8 checkpoint as an explicit capability
   fallback.** The file
   `qwen_image_edit_2509_fp8_e4m3fn.safetensors` is about 20.4GB and uses the
   plain fp8 storage path that works for the verified Qwen-Image-2512 base
   model. If successful, expose it honestly as `qwen-image-edit-2509`; do not
   silently serve 2509 under the 2511 model name.
2. Revisit 2511 int8 when PyTorch implements `aten::_int_mm` natively on MPS.
   The current error points to PyTorch issue
   `https://github.com/pytorch/pytorch/issues/141287`.
3. Consider a GGUF Q4 2511 route only after reviewing and pinning the required
   third-party ComfyUI-GGUF node. This adds a plugin/dependency surface and
   should not be installed ad hoc.
4. A remote CUDA ComfyUI backend is the cleanest way to retain full 2511
   quality if local MPS compatibility remains blocked.

## To do

- [x] Test `qwen_image_edit_2509_fp8_e4m3fn.safetensors` at 512×512 with the
      existing source image and a visually obvious edit.
- [x] Inspect the saved image, pixel statistics, logs, and peak free memory;
      successful execution alone is insufficient.
- [x] If it passes, add an explicit model route, installer download, admission
      estimate, unit coverage, and canonical wiki documentation.
- [x] Keep remote CUDA/larger-host execution as the supported 2511 path and
      retain the local bf16 admission refusal; the passing local route is 2509.
- [x] Decide whether to retain or remove the two failed 20.5GB checkpoints
      after the next investigation.
- [x] Run the full verification ladder and `bash scripts/ci_local.sh`.

## Definition of Done

- [x] At least one Qwen image-editing route produces a prompt-matching,
      non-degenerate edit without unsafe memory pressure.
- [x] The public model name accurately identifies the checkpoint generation.
- [x] Admission estimates match the verified peak and cannot be bypassed by a
      global dtype or fallback flag.
- [x] Installer, tests, task notes, and wiki facts agree.

## Resolution

The official `qwen_image_edit_2509_fp8_e4m3fn.safetensors` checkpoint completed
a real 512×512, 20-step edit on Apple Silicon MPS without `--force-fp16` or
`PYTORCH_ENABLE_MPS_FALLBACK`. Prompt
`88992f59-4fa8-425a-8be4-1824d1eef2c3` finished successfully in 697.8 seconds
and saved `portal__00011_.png`.

The source was the `PORTAL FIVE` fox-astronaut image. The instruction changed
the white spacesuit to vivid emerald green. The output is a valid,
non-degenerate RGB image: full 0–255 channel ranges, mean RGB
`(62.63, 85.15, 68.26)`, channel standard deviations
`(95.42, 79.25, 61.69)`, and 97,139 unique RGB values. The fox and dark-blue
setting remained recognizable. The model did reframe the composition and crop
most of the original text, so this route is instruction editing rather than
pixel-preserving retouching.

Starting free memory was 44.46GB and the lowest observed value was 10.55GB,
about 33.91GB consumed at peak. ComfyUI reported the plain-FP8 checkpoint
expanding to bf16 compute, so the route uses a conservative 38GB estimate plus
the existing 4GB headroom. The 2511 bf16 route remains at 60GB and is not
silently repointed.

`qwen-image-edit-2509` is now a distinct public route, the HTTP tool manifest
advertises `image_url`, and both HTTP dispatch endpoints forward it. The
Apple-Silicon installer now downloads the working 2512/2509 plain-FP8 set
instead of the unsafe bf16 pair. The confirmed-broken 2511 `fp8mixed` and
`int8_convrot` files were removed; both are recoverable from
`Comfy-Org/Qwen-Image-Edit_ComfyUI`.
