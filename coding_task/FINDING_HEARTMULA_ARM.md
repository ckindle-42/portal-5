# FINDING — HeartMuLa as a real music-screen arm (intake, install recipe, screen wiring)

**Date:** 2026-11-20 · **Lane:** `lane/heartmula-arm` · **Brief:** `coding_task/BRIEF_HEARTMULA_ARM.md`

Code complete, gates green, **unproven against the live system** — the orchestrator runs the
install and the re-screen (commands below). Nothing was downloaded or generated in this lane;
the port was cloned read-only into gitignored scratch (`coding_task/scratch/heartlib-mlx`).

## 1. Intake — newest release and MLX port (re-checked 2026-11-20)

Upstream (`HeartMuLa/heartlib` README news, https://github.com/HeartMuLa/heartlib, fetched
2026-11-20; org page https://huggingface.co/HeartMuLa):

- **Recommended pair:** `HeartMuLa/HeartMuLa-oss-3B-happy-new-year` (released 2026-02-13,
  "currently the best open-sourced model in terms of lyrics controllability and music quality")
  + `HeartMuLa/HeartCodec-oss-20260123` (released 2026-01-23, optimizes audio decoding).
  https://huggingface.co/HeartMuLa/HeartMuLa-oss-3B-happy-new-year ·
  https://huggingface.co/HeartMuLa/HeartCodec-oss-20260123
- `HeartMuLa-RL-oss-3B-20260123` (2026-01-23) is the RL tag-control variant; the README's
  recommendation for generation stays happy-new-year. Not chosen.
- `MuLaCover` (2026-09-16) is cover/remix (reference-audio conditioned), not text-to-music —
  out of scope for the screen's fixed prompts. `HeartMuLa-oss-7B` is still a TODO, unreleased.
- Tokenizer: the happy-new-year repo ships **no tokenizer.json**; it comes from
  `HeartMuLa/HeartMuLaGen` (`tokenizer.json` 9.1 MB + `gen_config.json`).
  https://huggingface.co/HeartMuLa/HeartMuLaGen — confirmed by the HF API file list and by an
  independent 2026-04 setup note (https://zenn.dev/sawacarac/scraps/d3784f547798b8) that ran
  exactly this pair through the same port.

MLX port (`Acelogic/heartlib-mlx`, https://github.com/Acelogic/heartlib-mlx):

- HEAD is still **`02dd2e22f6a1bf1a2f769a13f8af952a7a4e9cee`** (8 commits, last 2026-01-20) —
  the same pin `FINDING_MUSIC_SECOND_LISTENER.md` recorded; the port is stale but unchanged.
  Its README still names the old `HeartMuLa-oss-3B` + `HeartCodec-oss` repos; the install below
  keeps the README's *flow* with the current recommended repos (as the zenn note did).
- The old recipe's `tokenizer.json from HeartMuLa-oss-3B` step no longer works (file absent);
  the HeartMuLaGen source replaces it.

**Quantized weights — offered, but not for this port.** mlx-community publishes
`HeartMuLa-oss-3B-8bit` (4.94 GB), `-bf16` (7.88 GB), `HeartCodec-oss-fp16` (3.15 GB), `-fp32`
(6.29 GB) — all built for the **Swift** port `xocialize/mlx-heartmula-swift`
(https://github.com/xocialize/mlx-heartmula-swift, https://huggingface.co/mlx-community/HeartMuLa-oss-3B-8bit).
heartlib-mlx cannot load them: `HeartMuLa.from_pretrained` reads a single `model.safetensors`
and calls plain `model.load_weights` (no quantization config, no shard/index support —
`src/heartlib_mlx/heartmula/modeling.py:345-367` at the pin); the 8-bit bundle's
weight/scales/biases tensors need `nn.QuantizedLinear` modules this port does not have. The
Swift route would need a Swift toolchain and a CLI consumer outside this repo's uv/venv
installer pattern — a different brief. So the arm uses the port's own memory path: **convert
to MLX bf16** (the converter's default), which the porter's table puts at ~11 GB resident for
a 1-minute song. The 8-bit Swift tier (8.5 + 5.5 GB declared, 3× realtime on M5 Max) is
recorded here as the lighter alternative if the orchestrator ever wants it.

## 2. What the install does (`./launch.sh install-heartmula`)

Follows the install-music pattern: arm64-only, pinned detached checkout, own venv seeded once
from the upstream `uv.lock` (Python 3.12, preserved on re-run), forward-only security plan via
`scripts/engine_install_plan.py` (new `heartlib` service, no MCP service deps — the lock floors
carry the engine), idempotent marker-gated downloads and one-off conversion, arm64 import
verify with **no generation**. No launchd job, no port — this is a screen arm, not a service.

Layout (weights never on the main drive; `/Volumes/data01` mount is refused-if-absent):

```
~/.portal5/music/heartlib-mlx/            code @ 02dd2e2 + .venv        (~1–2 GB, main drive)
/Volumes/data01/media-screen/heartlib/
  ckpt/HeartMuLa-oss-3B-happy-new-year/   fp32 source, 4 shards          15.75 GB
  ckpt/HeartCodec-oss-20260123/           fp32 source, 2 shards           6.64 GB
  ckpt/tokenizer.json, gen_config.json    from HeartMuLaGen               9.1 MB
  ckpt-mlx/heartmula/model.safetensors    bf16 conversion                ~7.9 GB
  ckpt-mlx/heartcodec/model.safetensors   bf16 conversion                ~3.3 GB
```

(Sizes: HF API `?blobs=true` 2026-11-20; converted sizes corroborated by the mlx-community
bf16/fp16 bundle cards. data01 had 145 GiB free at intake.) Downloads run with
`HF_HOME=<weights>/hf-home` and `HF_HUB_DISABLE_XET=1` so no hub/xet cache lands on the main
drive. `HEARTMULA_WEIGHTS_ROOT` overrides the weights root (test seam; default stays data01).

Conversion was checked against the **real** happy-new-year `model.safetensors.index.json`
(289 tensors): every prefix (`audio_embeddings.weight`, `audio_head`, `backbone/decoder`
attn/mlp/norm names, `codebook0_head`, `muq_linear`, `projection`, `text_embeddings`,
`unconditional_text_embedding`) is handled by `convert_heartmula_weights`/`_map_heartmula_key`
or passes through to an identically-named MLX module attribute. Structural check only — the
conversion itself runs in the orchestrator's install.

## 3. Screen arm (`kind: heartlib`, row `heartmula3b`, rank 3)

`media_variant_screen.py` plans a spec + generated runner per prompt, exactly like the ACE
rows: the runner seeds `mx.random.seed(42)` (the port's sampling is `mx.random.categorical`;
`generate.py` has **no `--seed` flag**), then delegates to the port's own `generate.py` via
`runpy` with `--tags <caption> --lyrics <lyrics> --duration 30.0 --checkpoint
<Volumes/data01/media-screen/heartlib/ckpt-mlx> --dtype bfloat16 --output <run>/music/…wav`.
Upstream defaults are kept untuned: cfg-scale 1.5, temperature 1.0, top-k 50, max-memory 32 GB.
The harness samples RSS/free%/swap and records wall time the same way as every other arm;
load vs generation progress is in the row log (the port prints frame/Metal/RSS stats).

Arm characteristics the judge must know (read from the port's code, not measured):

- **Output is 48 kHz mono** — `HeartCodec.detokenize` returns `(batch, samples, 1)` and
  `generate.py` flattens it. The music canvas's "stereo" describes the ACE rows.
- **Audio EOS can end a clip before 30 s** (no `--ignore-eos` passed); the log's `Saved: …
  (X.XXs)` line is the real duration.
- Tokenizer resolves at `<checkpoint>/../ckpt/tokenizer.json` — the install layout satisfies it.
- The MiMo listen step pairs `heartmula3b` against `ace-xl17` automatically (rank-ordered).

## 4. Orchestrator runs

```bash
# (a) install — expect ~33–34 GB on data01, ~1–2 GB code+venv on the main drive
./launch.sh install-heartmula
```

Works: ends `verify-ok arm64` and `✅ HeartMuLa screen arm ready`, prints the data01 GB total;
`ckpt-mlx/{heartmula,heartcodec}/model.safetensors` exist. Fails: any ❌ (mount, venv, dep plan,
download, conversion) — the marker files make a re-run resume instead of re-download. First
conversion reads ~16 GB fp32 into RAM; run it without a bench in flight. `--dry-run` prints the
dep plan + sizes (needs the checkout to exist for the lock export, same as install-music).

```bash
# (b) music re-screen — incumbent + lm06 + nolm + heartmula3b, MiMo second listener
uv run python scripts/proofs/media_variant_screen.py --medium music --listen mimo-v2.6-pro
```

Works: `heartmula3b p1..p3` rows `ok` with a wav each, wall/peak-RSS/free-floor in
`screen_music_<date>.md`, and `listen_mimo-v2.6-pro_music_<date>.md` pairs heartmula3b vs
ace-xl17 with `audio_tokens` receipts. Fails: `exit1`/`no-output` rows (read
`logs/heartmula3b-p*.log` — checkpoint/tokenizer errors name themselves), free-floor collapse,
or a listener `CANNOT_PERCEIVE`.

**Pass** (doc's music bar, applied to heartmula3b): free % well above the incumbent's 22%
background on the same resident load, peak RSS under the XL+1.7B re-run, and MiMo + operator
accept prompts 1–3 — p2 an intelligible vocal, p3 still solo nylon (no kit, no singer).
**Fail:** free % collapses, p2 has no intelligible vocal, p3 grows drums or a voice, or the
row produces no wav. A pass makes it a candidate, not a seat change — that stays an
orchestrator/operator decision after two listener lineages agree.

## 5. Unproven here (orchestrator territory)

Install end-to-end (clone/venv/sweep plan/downloads/conversion), real RSS/free%/wall numbers,
audio quality and the mono/EOS behavior on real clips, MiMo's verdicts, and the happy-new-year
conversion producing audibly correct output (structural key check only in this lane).
