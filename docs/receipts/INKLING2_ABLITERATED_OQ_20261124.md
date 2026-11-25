# Inkling 2 Mini abliterated oQ receipt — blocked at source access

**Status:** blocked before quantization. Hugging Face returned `Access denied. This repository requires approval.` The BF16 source weights were not downloaded, so no quantized checkpoint or model proof exists. This is a checkpoint receipt, not a successful qualification.

## Candidate level and command

Candidate: **oQ4e with MTP preserved**. The existing reference recipe reports 16.847 GB / 15.690 GiB for language model, vision encoder, and DSpark draft together. That makes oQ4e the closest documented target to the requested roughly 16 GB footprint. The reference starts from NVFP4/MXFP8 expert weights; the requested source is presumed BF16, so equal output size and calibration memory are not established. Final selection remains pending source dtype inspection.

The installed live environment reports oMLX 0.8.3. Its `omlx` CLI has no `oq` subcommand; the quantizer entrypoint is `omlx.oq.quantize_oq_streaming`. If repository access is granted and the source dtype and memory preflight permit the run, the candidate command is:

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

## Disk and memory preflight

Observed before any quantization:

- `/Volumes/data01`: 1.8 TiB total, 1.7 TiB used, 152 GiB available, 92% capacity.
- Existing incompatible `orcarouter-inkling-2-mini-abliterated-mlx`: `du -sh` reported `15G`.
- Reference checkpoint path under `omlx-models` is a symlink, so `du -sh` reported `0B`; its README reports the actual component total as `16.847 GB / 15.690 GiB` including DSpark MTP.
- Output path `/Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp/` did not exist.
- `memory_pressure` reported 68,719,476,736 total bytes, 16,384-byte pages, and `System-wide memory free percentage: 94%`.
- No quantizer process ran, so peak RSS is **not measured**.

The attempted source destination `/Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated/` is 44K and contains only `README.md` and `LICENSE`; it has no model weights or `mtp.safetensors`.

## Proofs 1–4

1. **Tensor keys:** not run; output checkpoint was not created, so there is no key-set diff.
2. **Strict oMLX load and three prompts:** not run; no candidate checkpoint exists. No generated text is claimed.
3. **Lightning MTP acceptance:** not run; there is no candidate draft to load or acceptance rate to report against the reference.
4. **Decode tok/s:** not run; there is no candidate checkpoint measurement.

No BF16 source was available to delete after proof. The incompatible MLX export and the reference checkpoint were left untouched. Intended final output path remains `/Volumes/data01/omlx-staging/Inkling-2-Mini-abliterated-oQ4e-mtp/` and is absent.

## Commands and actual outputs

The source download attempt was:

```bash
/Users/chris/omlx-live/venv/bin/hf download orcarouter/Inkling-2-Mini-abliterated --local-dir /Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated
```

It exited 1 with:

```text
Still waiting to acquire lock on /Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated/.cache/huggingface/.gitignore.lock (elapsed: 0.1 seconds)
Still waiting to acquire lock on /Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated/.cache/huggingface/.gitignore.lock (elapsed: 0.1 seconds)
Still waiting to acquire lock on /Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated/.cache/huggingface/.gitignore.lock (elapsed: 0.1 seconds)
Error: Access denied. This repository requires approval.
Hint: set HF_DEBUG=1 as environment variable for full traceback.
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

After the Hugging Face account has approval for `orcarouter/Inkling-2-Mini-abliterated`, rerun the exact `hf download` command above. Continue only if the downloaded source has its safetensors and `mtp.safetensors`, verify the source dtypes, and check the resident-calibration requirement against the 52 GB peak-RSS ceiling. Then use the candidate quant command above and complete the four proofs before deleting the BF16 source. A download that still prints `Access denied` or a quantizer preflight/measurement above the ceiling means stop without deleting source data.
