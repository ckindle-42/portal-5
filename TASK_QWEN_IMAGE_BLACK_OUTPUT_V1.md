# TASK: Qwen-Image Produces Black Output on This Apple Silicon MPS Host

**Task ID:** TASK-QWEN-IMAGE-BLACK-OUTPUT-001
**Priority:** Normal (blocks the feature from actually being usable)
**Category:** Bug — correctness, not memory safety

---

## Context

2026-07-29: after fixing the Qwen-Image memory-crash incident (see
`KNOWN_LIMITATIONS.md` / `unit-known-limitations-qwen-image-bf16-crashes-on-
apple-silicon-mps`), a full end-to-end generation was run successfully —
no crash, model load + 20-step sampling + VAE decode + file save all
completed cleanly, RAM never dropped dangerously low. But the output image
is unusable: every pixel is exactly `(0, 0, 0)`, fully black.

This is a **separate bug** from the memory-crash fix. The memory-safety work
(fp8 diffusion + fp8_scaled text encoder, admission-control estimates) is
verified correct and should not be re-litigated by this task — the fix
there stands regardless of whether this bug gets resolved.

## What's already ruled out

Isolated via a sequence of fast 256x256 reproductions (see the wiki unit for
full detail):

- **Not under-sampling**: reproduces at both 4 steps and 20 steps.
- **Not a wiring mistake in `comfyui_mcp.py`**: reproduces using the *exact
  verbatim* official `qwen_image_basic_example.png` embedded workflow JSON
  (comfyanonymous.github.io/ComfyUI_examples/qwen_image/), not just this
  project's hand-built graph.
- **Not the `_scaled` text encoder**: reproduces identically with the text
  encoder swapped back to bf16 (`qwen_2.5_vl_7b.safetensors`), diffusion
  model still fp8. Not a quantization issue at all — this rules out the
  hypothesis that it's the same numerical-instability class as the earlier
  Wan2.2 `_fp8_scaled` `Float8_e4m3fn` crash.

## The one real lead

An isolated `VAELoader` -> `EmptySD3LatentImage` -> `VAEDecode` test (no
diffusion model in the graph at all) threw:

```
IndexError: tuple index out of range
  File "comfy/sd.py", line 781, in <lambda>
    self.memory_used_decode = lambda shape, dtype: (2200 if shape[2]<=4 else 7000) * shape[3] * shape[4] * ...
```

That shape-indexing code expects a 5-dimensional (video-style,
temporal-axis-included) latent tensor. ComfyUI's startup log confirms
Qwen-Image's VAE loads as `WanVAE` internally — the same class ComfyUI uses
for the Wan video pipeline's VAE. The full pipeline (with `KSampler` in
between) does NOT throw this same `IndexError`, so whatever `KSampler`/
`ModelSamplingAuraFlow` outputs must already be shaped 5D-compatibly — but
the VAE decode step is the strongest remaining suspect for where the values
go to zero, specifically on this MPS backend (a `WanVAE`-class decode path
CUDA/MPS numerical divergence).

## To do

- [ ] Get ComfyUI/PyTorch/MPS version info and check for known issues
      upstream (comfyanonymous/ComfyUI GitHub issues) — "Qwen-Image black
      output Apple Silicon" or "WanVAE MPS" are reasonable search starting
      points.
- [ ] If no known fix: trace `comfy/sd.py`'s VAE decode path for the
      `WanVAE`/Qwen-Image case, compare against the CUDA code path, look for
      an MPS-unsupported op (common culprits: certain conv3d configurations,
      certain dtype casts, certain reduction ops) that silently produces
      zeros instead of erroring on MPS.
- [ ] Try decoding through a *different* VAE class if ComfyUI exposes one
      for Qwen-Image specifically (vs. the shared WanVAE codepath) — may not
      exist; check the node's actual Python source
      (`comfy/ldm/...`/`comfy_extras/...` for the relevant VAE class).
- [ ] Consider whether `--force-fp16` (a flag already passed to this host's
      ComfyUI launch — see `~/ComfyUI/start.sh` / the launchd plist) is
      relevant — the earlier working TI2V-5B video generation used the same
      flag successfully with a *different* VAE (`wan2.2_vae.safetensors`,
      not zero-output), so this flag alone isn't sufficient explanation, but
      worth checking if TI2V-5B's VAE takes a different code path than
      Qwen-Image's WanVAE-class handling.
- [ ] Once root-caused: fix, then re-run the full end-to-end verification
      (real prompt, 1024x1024, 20 steps) and confirm the output is a real,
      non-degenerate image (not just "did not crash").
- [ ] Update `unit-known-limitations-qwen-image-bf16-crashes-on-apple-
      silicon-mps` (or supersede it) once resolved.

## Definition of Done

- [ ] Root cause identified for the all-black output.
- [ ] Fix applied and verified: a real `qwen-image-2512` generation produces
      a non-degenerate image matching the prompt.
- [ ] `qwen-image-2512-lightning` and `qwen-image-edit-2511` spot-checked
      too — they share the same VAE/diffusion architecture, so the same bug
      likely affects them, but this hasn't been directly confirmed.
