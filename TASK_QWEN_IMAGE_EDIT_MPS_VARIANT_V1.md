# TASK: Make Qwen Image Editing Usable on Apple Silicon MPS

**Task ID:** TASK-QWEN-IMAGE-EDIT-MPS-VARIANT-001
**Priority:** Normal
**Category:** Media capability / platform compatibility
**Status:** Open — resume from the recorded checkpoint

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

Both official artifacts are downloaded under
`~/ComfyUI/models/diffusion_models/` and can be reused without downloading
again:

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

- [ ] Test `qwen_image_edit_2509_fp8_e4m3fn.safetensors` at 512×512 with the
      existing source image and a visually obvious edit.
- [ ] Inspect the saved image, pixel statistics, logs, and peak free memory;
      successful execution alone is insufficient.
- [ ] If it passes, add an explicit model route, installer download, admission
      estimate, unit coverage, and canonical wiki documentation.
- [ ] If no local route passes, document remote CUDA as the supported 2511
      execution path and keep local bf16 admission refusal.
- [ ] Decide whether to retain or remove the two failed 20.5GB checkpoints
      after the next investigation.
- [ ] Run the full verification ladder and `bash scripts/ci_local.sh`.

## Definition of Done

- [ ] At least one Qwen image-editing route produces a prompt-matching,
      non-degenerate edit without unsafe memory pressure.
- [ ] The public model name accurately identifies the checkpoint generation.
- [ ] Admission estimates match the verified peak and cannot be bypassed by a
      global dtype or fallback flag.
- [ ] Installer, tests, task notes, and wiki facts agree.
