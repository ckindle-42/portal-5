# Inkling 2 Mini abliterated oQ receipt — round 2 repack complete; oQ pending

**Current status:** the BF16 source has been repacked into the base NVFP4/MXFP8 expert layout and passes oMLX 0.8.3 metadata preflight. The final oQ checkpoint and live model proofs are still absent, so this is not a successful qualification. The BF16 source and packed intermediate remain on `/Volumes/data01`.

## Round 1 — source and quantizer preflight

## Round-1 candidate level and blocked command

At round 1 the candidate was **oQ4e with MTP preserved**. The existing reference recipe reports 16.847 GB / 15.690 GiB for language model, vision encoder, and DSpark draft together. That makes oQ4e the closest documented target to the requested roughly 16 GB footprint. The reference starts from NVFP4/MXFP8 expert weights; this BF16 source was rejected by the installed quantizer and its calibration estimate exceeded the round-1 RSS ceiling. Final level selection was pending at that time.

The installed environment reports oMLX 0.8.3. Its `omlx` CLI has no `oq` subcommand; the quantizer entrypoint is `omlx.oq.quantize_oq_streaming`. This was the intended invocation for a compatible source; **do not run it against the BF16 source**, because the round-1 preflight rejected its layout and exceeded that round's ceiling:

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

## Round 1 orchestrator handoff (superseded by the round-2 repack)

At the end of round 1, do not run the candidate quant command against the BF16 source: its layout is rejected before tensor loading, and its metadata-derived resident calibration footprint exceeded the round-1 limit. Round 2 resolves the layout and estimate for the packed source; the final checkpoint still requires proofs 1–4 before deleting the BF16 source. No live oMLX/Ollama service was started from this worktree.

## Round 2 — repack complete; final oQ proofs pending

The new `scripts/inkling2_repack.py` reads the local BF16 tensors in expert-sized slices, quantizes only the expert matrices, and streams the output safetensors shards. It copies all non-expert tensors byte-for-byte, regenerates the model index, and copies the metadata files and MTP file. The script used the required `/Users/chris/omlx-live/venv` (oMLX 0.8.3, MLX 0.32.4). A first exploratory repack used the lane venv's MLX 0.32.2; that duplicate was moved aside and removed. The retained packed output was generated again with MLX 0.32.4.

### Base layout and range-read evidence

The public `thinkingmachines/Inkling-2-Mini` safetensors index maps **1,244** tensors to one shard of **19,526,019,168 bytes**. Its header was read using HTTP range requests only: the 8-byte prefix returned `206 bytes 0-7/19526019168`; the complete 148,416-byte header returned `206 bytes 0-148415/19526019168`. No base weight bytes were downloaded.

The header shows these expert formats:

- Layers 0–19 are ModelOpt NVFP4: `w13_weight` is `U8 [128,2304,1152]` with `F8_E4M3 [128,2304,144]` scales; `w2_weight` is `U8 [128,2304,576]` with `F8_E4M3 [128,2304,72]` scales. Each projection also has `F32 [128]` `*_weight_amax` and `F32 [1]` `*_weight_outer_scale_denominator` tensors.
- Layers 20–23 are MXFP8: `w13_weight` is `F8_E4M3 [128,2304,2304]` with `U8 [128,2304,72]` scales; `w2_weight` is `F8_E4M3 [128,2304,1152]` with `U8 [128,2304,36]` scales.

The base `config.json` declares `quant_method=modelopt`, `quant_algo=NVFP4`. oMLX 0.8.3's Inkling 2 patch uses a 2688 NVFP4 outer-scale denominator, and the repacker stores each expert's maximum absolute weight as `*_weight_amax`.

### Repack command and output

The full repack ran with one-second RSS sampling and a 54,000,000,000-byte stop threshold:

```bash
/Users/chris/omlx-live/venv/bin/python scripts/inkling2_repack.py \
  --source /Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated \
  --output /Volumes/data01/omlx-staging/inkling2-abl-packed
```

Actual converter summary:

```text
model_tensor_keys: 1244
output_shards: model-00001.safetensors .. model-00005.safetensors
model_storage_bytes: 19569698496
calibration_footprint_estimate_bytes: 19569698496
output: /Volumes/data01/omlx-staging/inkling2-abl-packed
process_exit: 0
peak_sampled_rss_bytes: 350814208
rss_samples: 47 (one second apart)
```

The source metadata and MTP were copied identically. The MTP SHA-256 is `7c3b651317f01f73bcf4e1dceba66ef8b7e1a1eac6bc171e882e690a4b10a1d2` on both source and output. The matching small files are `.gitattributes`, `LICENSE`, `README.md`, `chat_template.jinja`, `config.json`, `generation_config.json`, `processor_config.json`, `special_tokens_map.json`, `tokenizer.json`, and `tokenizer_config.json`.

### Repack proofs

**(a) Keys, dtypes, and shapes:** output headers contain the exact **1,244** base-index keys, with **0 output-only**, **0 reference-only**, **0 index/header**, and **0 shape** differences. All expert tensor dtypes match the base. There are **208 non-expert dtype differences**, all `F32` in the abliterated source/output versus `BF16` in the base. This follows the brief's copy-through rule: those non-expert tensors were copied unchanged. Their key-path counts are `attn_sconv.weight=24`, `mlp.gate.weight=24`, `mlp_sconv.weight=24`, `attn.k_sconv.weight=20`, `attn.v_sconv.weight=20`, and the eight `controllers.{attn,k,mlp,v}.{forget,gain}_weight` paths at 12 each. No expert dtype differences remain.

**(b) BF16 round-trip:** the script quantized selected source experts, dequantized them in memory, and reported these absolute errors. Expert IDs are shown in the listed order.

| Expert tensor | Format | IDs | Max absolute error | Mean absolute error |
|---|---|---|---|---|
| `layers.0.mlp.experts.w13_weight` | NVFP4 | 0, 1, 127 | 0.0002092719, 0.0004185140, 0.0002092645 | 0.0000232735, 0.0000236824, 0.0000263064 |
| `layers.19.mlp.experts.w2_weight` | NVFP4 | 0, 1, 127 | 0.0168805718, 0.0148228258, 0.0154854879 | 0.0015003390, 0.0013455955, 0.0013192758 |
| `layers.20.mlp.experts.w13_weight` | MXFP8 | 0, 1, 127 | 0, 0, 0 | 0, 0, 0 |
| `layers.23.mlp.experts.w2_weight` | MXFP8 | 0, 1, 127 | 0.0078125, 0.0078125, 0.0078125 | 0.0004870437, 0.0004783507, 0.0004861260 |

For a base-model sanity check, the local oQ reference checkpoint's preserved layer-0 NVFP4 `w13` expert 0 dequantized to finite values: max absolute value `0.1211204007`, mean absolute value `0.0164630674`. Its original BF16 base tensor is unavailable because the base weight was not downloaded, so error against that original is **N/A**; these values are only a dequantization sanity check.

**(c) oMLX metadata preflight:** `/Users/chris/omlx-live/venv/bin/python` constructed `omlx.oq._LazyTensorIndex` over the output. It accepted the layout and registered 88 virtual expert tensors, hiding 176 packed source sidecars. The five model shards were included; `mtp.safetensors` was excluded from calibration files.

**(d) Calibration estimate:** oMLX 0.8.3 reports **19,569,698,496 bytes** (19.570 decimal GB / 18.226 GiB) for the packed source. This metadata-derived estimate is below the 54 GB ceiling; it is not a quantizer RSS measurement.

### Disk, memory, and retained files

Before repacking, `du -sh` reported the BF16 source as `50G`; the packed and final oQ paths did not exist. `/Volumes/data01` had `102GiB` free at 95% capacity. `memory_pressure` reported 68,719,476,736 total bytes and 95% system-wide free memory.

After repacking, `du -sh` reported the BF16 source as `50G` and the packed directory as `19G`. The final oQ path `/Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp/` does not exist. `/Volumes/data01` has `83GiB` free at 96% capacity. Peak sampled RSS for the repacker was 350,814,208 bytes; the run stayed well below the 54,000,000,000-byte stop threshold.

The source and current packed directory remain in place because final oQ proofs have not passed. Neither the source nor current packed directory was deleted.

### Final oQ run and model proofs 1–4

The worker contract reserves full model calibration/load, prompt inference, MTP acceptance measurements, and throughput benchmarks for the orchestrator. For that reason the `quantize_oq_streaming` calibration was not started here, despite the now-accepted metadata and lower estimate. No final oQ model exists, so its key diff, strict load, three prompts, MTP acceptance, and decode tok/s are unproven.

After the orchestrator runs the quantizer, the strict oMLX Inkling loader is `omlx.patches.inkling2.vlm.load`; its internal `mlx_lm.utils.load_model` call defaults to `strict=True`. The MTP acceptance and throughput harness path was not present in this lane, so use the operator's existing harness identically against the candidate and `/Volumes/data01/omlx-models/Inkling-2-Mini-oQ4e-mtp`. Keep both the BF16 source and packed directory until model proofs 1–4 pass.

The following copy-pasteable command runs the quantizer in oMLX 0.8.3, samples the child process RSS once per second, interrupts if RSS crosses 54,000,000,000 bytes, and has no wall-clock timeout:

```bash
/Users/chris/omlx-live/venv/bin/python - <<'PY'
import signal
import subprocess
import sys
import time

code = '''from omlx.oq import quantize_oq_streaming
quantize_oq_streaming(
    model_path="/Volumes/data01/omlx-staging/inkling2-abl-packed",
    output_path="/Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp",
    oq_level=4,
    enhanced=True,
    preserve_mtp=True,
    dtype="bfloat16",
    imatrix_cache_path="/Volumes/data01/hf-cache/Inkling-2-Mini-abliterated-oQ4e-imatrix.npz",
)
'''
process = subprocess.Popen([sys.executable, "-c", code])
peak_kb = 0
samples = 0
while process.poll() is None:
    result = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(process.pid)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        rss_kb = int(result.stdout.strip())
        peak_kb = max(peak_kb, rss_kb)
        samples += 1
        if rss_kb * 1024 > 54_000_000_000:
            print(f"RSS_LIMIT_EXCEEDED bytes={rss_kb * 1024}", flush=True)
            process.send_signal(signal.SIGINT)
            break
        if samples % 15 == 0:
            print(f"rss_bytes={rss_kb * 1024} sampled_peak_bytes={peak_kb * 1024}", flush=True)
    time.sleep(1)
exit_code = process.wait()
print(f"exit_code={exit_code} peak_sampled_rss_bytes={peak_kb * 1024} samples={samples}")
sys.exit(exit_code)
PY
```

### Code gate evidence

The test was run before implementation and failed at collection as expected:

```text
ModuleNotFoundError: No module named 'scripts.inkling2_repack'
1 error during collection; exit code 2
```

After implementation, the focused test passed:

```text
2 passed in 0.26s
```

The full required gates completed successfully:

```text
pytest tests/unit/: 3777 passed, 21 skipped, 7 warnings in 129.03s
ruff check .: All checks passed!
ruff format --check .: 1700 files already formatted
mypy portal/: Success: no issues found in 735 source files
scripts/complexity_report.py --gate: GATE OK
  data_lines: 10,425 <= 13,370
  god_lines: 64,467 <= 71,202
  unwired_scripts: 25 <= 25
  identical_pairs: 0 <= 0
  committed_blob_bytes: 1,792,894 <= 1,873,616
reported, not gated: prose 59,697 (baseline 60,282), god_funcs 555 (baseline 546)
```
