# Inkling 2 Mini abliterated oQ receipt — blocked at quantizer preflight

**Status:** source downloaded, stopped before quantization. The source is BF16, but the installed oMLX 0.8.3 Inkling 2 oQ registration rejects its expert layout, and its resident calibration footprint estimate exceeds the ~52 GB ceiling. No quantized checkpoint or model proof exists. This is a checkpoint receipt, not a successful qualification.

## Candidate level and command

Candidate: **oQ4e with MTP preserved**. The existing reference recipe reports 16.847 GB / 15.690 GiB for language model, vision encoder, and DSpark draft together. That makes oQ4e the closest documented target to the requested roughly 16 GB footprint. The reference starts from NVFP4/MXFP8 expert weights; this BF16 source is rejected by the installed quantizer and its calibration estimate exceeds the RSS ceiling. No final level was selected.

The installed live environment reports oMLX 0.8.3. Its `omlx` CLI has no `oq` subcommand; the quantizer entrypoint is `omlx.oq.quantize_oq_streaming`. This is the intended invocation for a compatible source under the memory limit; **do not run it against the current BF16 source**, because the preflight above rejects its layout and exceeds the ceiling:

```bash
/usr/bin/time -l /Users/chris/omlx-live/venv/bin/python - <<'PY'
from omlx.oq import quantize_oq_streaming

quantize_oq_streaming(
    model_path="/Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated",
    output_path="/Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp",
    oq_level=4,
    enhanced=True,
    preserve_mtp=True,
    dtype="bfloat16",
    imatrix_cache_path="/Volumes/data01/hf-cache/Inkling-2-Mini-abliterated-oQ4e-imatrix.npz",
)
PY
```

`enhanced=True` selects the `e` path and `preserve_mtp=True` retains `mtp.*`. oMLX's source documents that Inkling 2 calibration is resident and does not build a smaller proxy. The general 3–4 GB streaming note therefore does not establish this source's peak RSS. Do not start this command until the actual source dtype/size and the 52 GB peak-RSS constraint are reconciled. `/usr/bin/time -l` records maximum RSS after exit; it does not enforce a hard cap.

## Source and quantizer preflight

The gated download succeeded on the follow-up dispatch. Header-only safetensors inspection found `model_type=inkling2_loop`, BF16 and F32 tensors in the model shards, and a BF16 `mtp.safetensors`. Across all three files the headers report 26,684,456,592 BF16 elements and 22,082,560 F32 elements. The representative expert key is `model.llm.layers.0.mlp.experts.w13_weight`, BF16, shape `[128, 2304, 2304]`.

The oMLX 0.8.3 index constructor failed before loading any tensor data:

```text
ValueError: Unrecognized Inkling 2 expert layout: model.llm.layers.0.mlp.experts.w13
```

This was independently checked against the raw safetensors header and `omlx/patches/inkling2/oq_virtual.py`: the header contains the BF16 `*_weight` key with no `*_weight_scale`; that registrar accepts packed NVFP4 U8 weights with F8_E4M3 scales, or MXFP8 F8_E4M3 weights with U8 scales. The BF16 expert layout matches neither. The full `quantize_oq_streaming` call was not started.

The quantizer's `_source_weight_files` excludes the bundled draft for calibration. Its `_calibration_footprint_bytes` rule returns the source storage size for Inkling 2. The two model shards total **52,821,579,912 bytes (52.822 decimal GB; 49.194 GiB)**, which is **821,579,912 bytes above** the 52,000,000,000-byte ceiling used here. This is a metadata-derived footprint estimate, not a measured process RSS; no quantizer peak RSS was observed.

## Disk and memory preflight

Observed after download and before any quantization:

- `/Volumes/data01`: 1.8 TiB total, 1.7 TiB used, 102 GiB available, 95% capacity.
- Existing incompatible `orcarouter-inkling-2-mini-abliterated-mlx`: `du -sh` reported `15G`.
- Reference checkpoint path under `omlx-models` is a symlink, so `du -sh` reported `0B`; its README reports the actual component total as `16.847 GB / 15.690 GiB` including DSpark MTP.
- Output path `/Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp/` did not exist.
- Source path `/Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated/` measured `50G` before and after metadata inspection; the output path remained absent.
- `memory_pressure` reported 68,719,476,736 total bytes, 16,384-byte pages, and `System-wide memory free percentage: 95%` immediately before the calibration estimate.
- No quantizer process ran, so peak RSS is **not measured**. The metadata estimate exceeds the limit, so quantization was stopped before load.

The source directory contains the two model shards and `mtp.safetensors` at the requested `/Volumes/data01` location. It was retained because the proofs did not pass.

## Proofs 1–4

1. **Tensor keys:** not run; output checkpoint was not created, so there is no key-set diff.
2. **Strict oMLX load and three prompts:** not run; no candidate checkpoint exists. No generated text is claimed. The worker contract reserves live model runs for the orchestrator.
3. **Lightning MTP acceptance:** not run; there is no candidate draft to load or acceptance rate to report against the reference. This model measurement is orchestrator-only.
4. **Decode tok/s:** not run; there is no candidate checkpoint measurement. This benchmark is orchestrator-only.

The BF16 source was not deleted because the proofs did not pass. The incompatible MLX export and the reference checkpoint were left untouched. Intended final output path remains `/Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp/` and is absent.

## Commands and actual outputs

The source download command was:

```bash
/Users/chris/omlx-live/venv/bin/hf download orcarouter/Inkling-2-Mini-abliterated --local-dir /Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated
```

On this dispatch it exited 0 with:

```text
path=/Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated
```

The exact quantizer preflight summary was:

```text
model_type: inkling2_loop
weight_files: ['model-00001-of-00002.safetensors', 'model-00002-of-00002.safetensors']
weight_shard_bytes: [48676607320, 4144972592]
calibration_storage_bytes: 52821579912
calibration_footprint_bytes: 52821579912
calibration_footprint_decimal_GB: 52.821579912
calibration_footprint_GiB: 49.19392979890108
52GB_decimal_limit_bytes: 52000000000
excess_over_52GB_bytes: 821579912
```

The separate header scan reported:

```text
model-00001-of-00002.safetensors: BF16 379 tensors; F32 267 tensors
model-00002-of-00002.safetensors: BF16 455 tensors; F32 15 tensors
mtp.safetensors: BF16 54 tensors
model.llm.layers.0.mlp.experts.w13_weight BF16 [128, 2304, 2304]
```

Other command outputs:

```text
$ /Users/chris/omlx-live/venv/bin/omlx --version
0.8.3

$ du -sh /Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated-mlx /Volumes/data01/omlx-models/Inkling-2-Mini-oQ4e-mtp /Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp
15G  /Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated-mlx
0B   /Volumes/data01/omlx-models/Inkling-2-Mini-oQ4e-mtp
du: /Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp: No such file or directory
```

The `0B` is the symlink measurement, not the checkpoint size; the reference README is the source for its stated 16.847 GB / 15.690 GiB.

## Orchestrator next step

Do not rerun the candidate quant command against this source and oMLX 0.8.3: the source layout is rejected before tensor loading, and its metadata-derived resident calibration footprint exceeds the brief's memory ceiling. Resume only if the orchestrator resolves both constraints within the brief's oMLX version and memory limits. Then the orchestrator must complete proofs 1–4 against the resulting checkpoint before deleting the retained BF16 source. No live oMLX/Ollama service was started from this worktree.
