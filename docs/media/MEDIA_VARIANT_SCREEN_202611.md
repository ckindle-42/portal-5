# Media variant screen — smaller MLX builds (2026-11)

**Written:** 2026-11-19 as a screen plan. A judged-results section for the 2026-11-20 runs was added the same week. That judgment changed no seat and no production config. The operator's own verdicts on those runs are recorded in "Operator verdicts (2026-11-20)" at the end of this document; they also changed no seat and no production config.
**Host the screen is for:** 64 GB Apple Silicon, oMLX (`:8085`) and Ollama (`:11434`) co-resident, ~56 GB GPU wired limit. Measured live the same day (orchestrator, stack up): image **FLUX.2 [klein] 4B q8 peak 9 GB**; video **LTX-2.5 q4, 512×320-class, worker ~9 GB RSS, system free ≥52%**; music **ACE-Step 1.5 XL-Turbo, system free fell to 22%** (heaviest). Roster reasoning: `docs/media/MEDIA_OVERHAUL_RESEARCH.md`.
**Incumbent code (repo, not re-measured here):** image `flux2-klein-4b` at `-q 8`, 4 steps (`portal/modules/media/tools/mflux_mcp.py`); video `ltx-2-mlx generate --distilled --low-ram` on `dgrauet/ltx-2.5-mlx-q4` (`portal/modules/media/tools/video_mlx_mcp.py`); music `acestep-v15-xl-turbo` + `acestep-5Hz-lm-1.7B`, `use_mlx_dit=True`, LM `backend=mlx` (`portal/modules/media/tools/music_worker.py`).

Every number below is tagged **Vendor** (lab, porter, or model-card self-measurement), **User** (a person reporting their own machine), or **Repo** (this checkout). None of the candidate peaks were measured on this host. A screen row counts only after the orchestrator runs the command and reads RSS.

Pins read 2026-11-19 from GitHub `main`: mflux `014252f` (2026-11-18), ltx-2-mlx `747b30e` (2026-11-01), FastVideo `c938a8a` (2026-11-15), ACE-Step-1.5 `ca1e85f` (2026-08-29), heartlib-mlx `02dd2e2` (2026-01-21). PyPI `mflux` is still **0.24.0**; Iris and `--small-text-encoder` are on git `main`, so the image screen installs from that pin, not from PyPI.

---

## How a row is judged

Run **one candidate at a time**. Leave oMLX and Ollama as they were for the 2026-11-19 measurement, and write down what `ps` shows resident before the run. A quiet-host re-run is a second row, not a substitute.

Record, per prompt: wall time, `/usr/bin/time -l` maximum resident set size (bytes ÷ 1024³ = GB), system free % from `memory_pressure` at the peak, exit code, and the output path. If the process is killed or free memory hits 0, that candidate **fails**. Do not shrink the canvas and call the retry a pass.

**Fixed canvas**

| Medium | Geometry | Seed | Steps |
|---|---|---|---|
| Image | 1024×1024 | 42 | the candidate's distilled default (table) |
| Video | 512×320, 97 frames, 24 fps | 42 | distilled / the model's own 3-step schedule |
| Music | 30.0 s, 48 kHz stereo wav | 42 | 8 for every ACE-Step turbo; HeartMuLa's own default |

97 = 4×24+1 and 512×320 divides by 32, so Wan-family runners accept the video canvas. FastMetal's published times are at 480×832 or 704×1280; those are **not** this screen's pass line.

**Quality, after memory is recorded**

Images: the seated vision model looks at the three PNGs blind to which checkpoint made them and scores text accuracy, anatomy/geometry, and texture. The operator looks at the same files. A candidate passes quality only if it is not worse than the incumbent re-run on the same three prompts.
Video: `ffprobe` must show a video stream (and an audio stream for any LTX row). The operator watches all three clips. Silent models cannot win a row whose prompt asks for sound; they can win only the "silent draft" note.
Music: the operator listens. No seated model here listens to audio; do not ask the generator to grade itself.

---

## Fixed prompts

**Image** (all three, 1024×1024, seed 42)

1. `A corner bakery at dawn, wet cobblestones, warm window light. A wooden sign above the door reads PORTAL 5 in cream capital letters. Photograph.`
2. `Macro studio photograph of a mechanical wristwatch, polished steel, visible gears, soft box light, black background.`
3. `A red fox asleep in fresh snow, golden hour, individual fur strands, pine trees out of focus.`

**Video** (512×320, 97 frames, 24 fps, seed 42)

1. `Ocean waves hit dark basalt rocks at sunset. Water crashes and pulls back. The soundtrack is waves and wind, no music.`
2. `A heavy wooden door creaks slowly open toward the camera. Hinges squeak. Dust in a shaft of light.`
3. `A person in a red coat walks left to right across a snowy path. Footsteps crunch. Camera stays fixed.`

**Music** (30 s, seed 42)

1. Caption `sparse acoustic guitar and soft brushed snare, 72 bpm, A minor, no vocals`. Lyrics empty.
2. Caption `upbeat indie pop, female vocal, 120 bpm, G major`. Lyrics:

```
[verse]
Streetlight on the wet stone
I am walking home alone

[chorus]
Hold the line, hold the light
We are louder than the night
```

3. Caption `solo nylon-string guitar, slow, no drums, no bass, no vocals`. Lyrics empty. This is the failure case: extra drums or a singer is a miss.

---

## Image

Incumbent to re-run first, same canvas: `flux2-klein-4b`, `-q 8`, 4 steps, `--low-ram`. Live peak on this host: **9 GB** (resolution of that 9 GB was not in the brief; the screen re-measures it at 1024²).

Rank is "worth a pull on this host", smallest credible peak first. FLUX 3 is listed and then **not pulled**: at 1024² it is slower and not smaller than 9 GB.

| Rank | Id | Quant / steps | Expected peak | Time (published) | License | Runner | Quality evidence | Claim |
|---|---|---|---|---|---|---|---|---|
| 1 | `iris-3b` Turbo | `-q 8`, 4 steps | **5.3 GB** while generating, **8.8 GB** while the text encoder is still loaded, 1024² | 18.4 s / 4 steps, M4 Pro 64 GB | Apache-2.0 (DiT and Qwen3-VL-4B encoder) | `mflux-generate-iris` on mflux `014252f` | Same-seed PSNR **34.6 dB** vs the porter's own bf16. No head-to-head vs FLUX.2 klein | **Vendor** (mflux Iris README, fetched 2026-11-19) |
| 2 | `flux2-klein-4b` + `--small-text-encoder` | `-q 4`, 4 steps | Weights **3.6 GB** (q8 drops 8.6→5.8 GB). Saved 4-bit peak **3.7 GB at 512²**. At 1024² `--low-ram` the porter says the peak **does not fall**, because denoise + VAE set it | 1024² bf16 ~20 s vs ~27 s with the 4B encoder, M4 Pro 64 GB | Apache-2.0 (klein 4B, Qwen3-0.6B, AiArtLab adapter) | `mflux-generate-flux2` | Porter: tag prompts that look anime on the native encoder can come out photographic. Prompt cap 256 tokens | **Vendor** (mflux FLUX.2 README, fetched 2026-11-19) |
| 3 | `z-image-turbo` | 4-bit, 8–9 steps | **5.5 GiB** at 1024² | 41–49 s, M6 Mac mini 32 GB, mflux 0.23, 2026-10-25 | Apache-2.0 | `mflux-generate-z-image-turbo` | Teamday ranks it behind FLUX.2 klein 4B for drafts (15–16 s, 8.2–10.7 GiB on that same machine) | **Vendor/bench** (teamday.ai, 2026-11-13). **User**, different canvas: @shermstudio, 2026-11-12, 9 steps, 1536×640, **~26 GB** on a Mac Studio Ultra — not a 4-bit 1024² figure |
| — | `qwen-image-2.1-turbo` | 4-bit or 6-bit, 8 steps | **User** @aijoey 2026-10-10, 24 GB M4: 4-bit 512² **4.71 GB / 52 s**; 6-bit 512² **6.34 GB**; 6-bit 1024² **8.45 GB / 3 m 40 s**. Teamday 4-bit 1024² **6.9 GiB / 46–47 s** | same | Qwen Research License (non-commercial / restricted) | `mflux-generate-qwen-2.1 --model qwen-image-2.1-turbo` | @aijoey: 6-bit "0.999 match" to official bf16 (his measurement). Maintainer README: bf16 text encoder stays resident and peak is **~46 GB** unless a path that actually quantizes or swaps it is used | **User** (@aijoey, post `2108776632433459426`) and **bench** (teamday). The 46 GB line is **Vendor** and is why this is not rank 1: the screen rejects the row if RSS stays near 46 GB |
| reject | `flux3-image-klein` | `-q 4` / `-q 8`, 16 steps | Maintainer, before strip-VAE: q4 **18.5 GB**, q8 **22.8 GB**, 1024², ~7 s/step on M4 Pro. Teamday 4-bit 1024² **10.9–11.9 GiB / 58 s**. flux3-mlx porter: 8-bit 1024² **14.3 GB** (11.0 with `--low-memory`), ~115 s, M4 Pro 48 GB. Separate porter on M5 32 GiB: Q8 **7.46 GiB** but that is another runner and LPIPS vs FP32, not a look test | slower than klein 4B on the teamday machine (58 s vs 15–16 s) | FLUX Kommunity v1.0, gated, &lt;$5M commercial | `mflux-generate-flux3` or `flux3-mlx` | VisualInference: **no 4-bit repo on purpose** (grain, design changes). devin-lai: Q4 LPIPS 0.055 and an extra pencil in a type test | **Vendor** throughout. Not smaller than the 9 GB incumbent at 1024² on the mflux numbers. Do not pull it in this screen |
| reject | full `Wan` / `FLUX.2-klein-9b` | — | klein-9b is a larger sibling. Not a footprint cut | — | 9B is non-commercial | — | — | — |

Iris q4 is measured by the same porter at **4.4 GB** generate-peak and **20.7 dB** PSNR (visibly softer). Screen it only if q8 already fits and the operator wants the next cut. Do not start there.

### Image commands

Install once, outside the Portal venv:

```bash
uv tool install --reinstall --from "git+https://github.com/mflux-community/mflux@014252f22408" mflux
mkdir -p /tmp/media-variant-screen/image
```

Incumbent, then rank 1, then rank 2, then rank 3. Swap the prompt text for prompts 2 and 3. `hf` downloads on first run.

```bash
# incumbent
/usr/bin/time -l mflux-generate-flux2 \
  --model flux2-klein-4b -q 8 --low-ram --steps 4 --seed 42 \
  --width 1024 --height 1024 \
  --prompt "A corner bakery at dawn, wet cobblestones, warm window light. A wooden sign above the door reads PORTAL 5 in cream capital letters. Photograph." \
  --output /tmp/media-variant-screen/image/klein4b-q8-p1.png

# rank 1 — Iris Turbo q8
/usr/bin/time -l mflux-generate-iris \
  --model iris-3b -q 8 --seed 42 --width 1024 --height 1024 \
  --prompt "A corner bakery at dawn, wet cobblestones, warm window light. A wooden sign above the door reads PORTAL 5 in cream capital letters. Photograph." \
  --output /tmp/media-variant-screen/image/iris-q8-p1.png

# rank 2 — same klein 4B, 4-bit, 0.6B text encoder
/usr/bin/time -l mflux-generate-flux2 \
  --model flux2-klein-4b -q 4 --small-text-encoder --low-ram --steps 4 --seed 42 \
  --width 1024 --height 1024 \
  --prompt "A corner bakery at dawn, wet cobblestones, warm window light. A wooden sign above the door reads PORTAL 5 in cream capital letters. Photograph." \
  --output /tmp/media-variant-screen/image/klein4b-q4-smallte-p1.png

# rank 3
/usr/bin/time -l mflux-generate-z-image-turbo \
  -q 4 --steps 9 --seed 42 --width 1024 --height 1024 \
  --prompt "A corner bakery at dawn, wet cobblestones, warm window light. A wooden sign above the door reads PORTAL 5 in cream capital letters. Photograph." \
  --output /tmp/media-variant-screen/image/zimage-q4-p1.png
```

Qwen is optional and stops if the first image's RSS is above 12 GB:

```bash
/usr/bin/time -l mflux-generate-qwen-2.1 \
  --model qwen-image-2.1-turbo -q 4 --low-ram --steps 8 --seed 42 \
  --width 1024 --height 1024 \
  --prompt "A corner bakery at dawn, wet cobblestones, warm window light. A wooden sign above the door reads PORTAL 5 in cream capital letters. Photograph." \
  --output /tmp/media-variant-screen/image/qwen21-turbo-q4-p1.png
```

**Pass:** max RSS under the incumbent's re-measured 1024² RSS, all three PNGs exist, vision-model + operator scores are not worse. **Fail:** OOM, missing text on prompt 1 that the incumbent rendered, or RSS ≥ incumbent.

---

## Video

Incumbent: `dgrauet/ltx-2.5-mlx-q4`, `--distilled --low-ram`, 512×320, 97 frames. Live: worker **~9 GB RSS**, system free **≥52%**, and the clip has audio. ltx-2-mlx `747b30e` (2026-11-01) is newer than the 2026-10-22 `v0.18.0` release; re-run the incumbent on that pin before treating 9 GB as the bar. There is **no MLX q3** of LTX-2.5. The GGUF Q3 files (`Abiray/LTX-2.5-Distilled-GGUF`) have no MLX runner and are out.

| Rank | Id | Quant / steps | Expected peak | Time (published) | License | Runner | Quality evidence | Claim |
|---|---|---|---|---|---|---|---|---|
| 1 | `FastVideo/FastMetal-1.3B-QAD` | INT8 QAT, 3-step DMD2, from Wan2.1-T2V-1.3B | **3.87 GiB** at 480×832×81 (fast mode **3.20 GiB**) on M4 Max 36 GB | 110.14 s cold; fast mode 45.19 s | Apache-2.0 | `mlx_wan_prompt_to_video.py` in FastVideo `c938a8a` | **Silent.** No user look-test vs LTX-2.5 found | **Vendor** (Hao AI Lab, 2026-08-10, https://haoailab.com/blogs/fastmetal/). The script is still in the 2026-11-15 tree. August is outside the preferred window; it is the only MLX clip with a published peak clearly under 9 GB |
| 2 | `FastVideo/FastMetal-5B-QAD` | INT8 QAT, 3-step, Wan2.2-TI2V-5B | **9.34 GiB** at 704×1280×81; fast mode **7.97 GiB**. Air re-test (M5, 24 GB) stayed within a few hundred MiB of that | 151.42 s cold; fast 47.24 s (fast reuses a prompt cache — not a cold number) | Apache-2.0 | `mlx_wan22_generate.py` | **Silent.** At 720p the peak matches our 512×320 LTX number, so the matched-canvas run is the one that matters. Full unquantized mlx-video of the same 5B peaked at **56.4 GB** on an M3 Max 64 GB (rotecodefraktion, 2026-10-10) — do not run that conversion | **Vendor** (same Hao post). The 56.4 GB figure is a **user/blog measurement** of the *unquantized* port and is a reject |
| keep | `dgrauet/ltx-2.5-mlx-q4` | int4 distilled + `--low-ram` | This host: **~9 GB RSS** at 512×320-class. Pack download ~47 GB (README); HF card shows a larger tree because dev and distilled transformers are both in the repo | User @Hoagie78Ai, 2026-11-19: M1 Max 64 GB, ~27 min for a **12 s** clip with a personal LoRA. Not a memory figure | LTX-2.x Community (&lt;$10M) | `ltx-2-mlx` `747b30e` | Only candidate here with **synchronized audio**. Phosphene 5.0.20 (2026-11-13) claims **5.7 GB vs 9 GB** on a 16 GB Mac, frames unchanged; 5.0.25 claims decode peaks cut on &gt;32 GB Macs. That is a closed app | **Repo/live** for 9 GB. **User** for the 27 min (@Hoagie78Ai, posts 2026-11-15 and 2026-11-19). **Developer claim** for 5.7 GB, relayed by @cutetoxicguy 2026-11-15 (`2121875860617879936`). Do not treat 5.7 GB as an ltx-2-mlx result |
| reject | `dgrauet/ltx-2.3-mlx-q4` | int4, README "fits 16 GB" | Smaller **download** (~12 GB) than the 2.5 pack. Older model, not a newer one | — | LTX-2 community | ltx-2-mlx | README comfort note for 97×512×320 on 32 GB is the porter's, with no RSS | **Vendor.** Skip |
| reject | Wan2.2 TI2V-5B via `mlx-video` unquantized, or A14B | Q8 disk 18–23 GB | 56.4 GB peak on the published M3 Max run | ~18 min for 41 frames at 1280×704 | Apache-2.0 | Blaizzy mlx-video | Photoreal claims are real and the memory is not usable next to resident LLMs | **User/blog** 2026-10-10 |

### Video commands

```bash
mkdir -p /tmp/media-variant-screen/video
# incumbent, Portal-installed ltx-2-mlx tree at the screen pin. Accept the LTX and Gemma terms once if a model pull returns 401.
/usr/bin/time -l "$HOME/.portal5/video-mlx/ltx-2-mlx/.venv/bin/ltx-2-mlx" \
  ltx-2-mlx generate --distilled --low-ram \
  --model dgrauet/ltx-2.5-mlx-q4 \
  --prompt "Ocean waves hit dark basalt rocks at sunset. Water crashes and pulls back. The soundtrack is waves and wind, no music." \
  --width 512 --height 320 --frames 97 --frame-rate 24 --seed 42 \
  --output /tmp/media-variant-screen/video/ltx25-q4-p1.mp4
```

FastMetal checkouts (clone once, do not `uv pip install` into the Portal venv):

```bash
git clone --branch main https://github.com/hao-ai-lab/FastVideo.git /tmp/FastVideo-screen
git -C /tmp/FastVideo-screen checkout c938a8aa2b85
cd /tmp/FastVideo-screen
uv venv --python 3.12
uv pip install -e '.[mlx]'
hf download FastVideo/FastMetal-1.3B-QAD --local-dir /tmp/FastMetal-1.3B-QAD
hf download FastVideo/FastMetal-5B-QAD --local-dir /tmp/FastMetal-5B-QAD
```

Rank 1 and rank 2 at the **screen** canvas, not the lab's 720p canvas. No `--fast` on the scored run (fast interpolates frames). A second `--fast` run may be timed afterwards and labelled interpolated.

```bash
cd /tmp/FastVideo-screen
/usr/bin/time -l .venv/bin/python examples/inference/basic/mlx_wan_prompt_to_video.py \
  --model-root /tmp/FastMetal-1.3B-QAD --mlx-checkpoint /tmp/FastMetal-1.3B-QAD \
  --height 320 --width 512 --num-frames 97 --seed 42 \
  --prompt "Ocean waves hit dark basalt rocks at sunset. Water crashes and pulls back. The soundtrack is waves and wind, no music." \
  --output-path /tmp/media-variant-screen/video/fastmetal13-p1.mp4

/usr/bin/time -l .venv/bin/python examples/inference/basic/mlx_wan22_generate.py \
  --mlx-checkpoint /tmp/FastMetal-5B-QAD \
  --text-encoder-root /tmp/FastMetal-5B-QAD \
  --vae-root /tmp/FastMetal-5B-QAD/vae \
  --height 320 --width 512 --num-frames 97 --seed 42 \
  --prompt "Ocean waves hit dark basalt rocks at sunset. Water crashes and pulls back. The soundtrack is waves and wind, no music." \
  --output-path /tmp/media-variant-screen/video/fastmetal5b-p1.mp4
```

If `mlx_wan22_generate.py` rejects `--seed` or `--output-path`, run `.venv/bin/python examples/inference/basic/mlx_wan22_generate.py --help` and keep height 320, width 512, frames 97. Do not fall back to 720p for the scored row.

**Pass for a silent model:** RSS under the incumbent's re-measured RSS, video stream present, operator accepts the picture **knowing there is no audio**. It does not replace LTX-2.5 if the task needs sound. **Pass for staying on LTX:** no silent candidate is both smaller and acceptable to the operator.

---

## Music

Incumbent: `acestep-v15-xl-turbo` (4B DiT, 8 steps) + `acestep-5Hz-lm-1.7B`, MLX DiT and MLX LM, under `~/.portal5/music/ACE-Step-1.5`. Live signal was system free **22%**, not a process RSS. The screen records both RSS and free %.

Vendor weight table (ACE-Step README / DeepWiki, not a Mac RSS): 2B turbo DiT **~4.7 GB**, XL turbo **~9 GB**; LM 0.6B **~1.2 GB**, 1.7B **~3.4 GB**, 4B **~8 GB**. Official GPU tiers put 2B turbo + 0.6B LM in the 6–12 GB class and XL without offload at ≥20 GB. Those are **Vendor** GPU notes.

**User**, 原野, 2026-11-14, 48 GB Mac (https://note.com/fukuoka_ai_c/n/n1c501db0d2d6): load climbed to **20.75 GB** with DiT-only (LM off), half precision, MLX cache capped at 1 GB; 30 s of BGM in about **9 s**; swap grew. That is one reduced config on a smaller machine, not a measurement of XL+1.7B on this host.

| Rank | Id | Quant / steps | Expected peak | Time (published) | License | Runner | Quality evidence | Claim |
|---|---|---|---|---|---|---|---|---|
| 1 | `acestep-v15-turbo` + `acestep-5Hz-lm-0.6B` | bf16/MLX as the runtime ships them, 8 steps, LM on | Weights suggest a cut vs XL+1.7B. No 64 GB RSS found. 原野's DiT-only load hit 20.75 GB on a 48 GB Mac | Vendor: turbo is the fast default. 原野 ~9 s for 30 s BGM, DiT-only | MIT | existing ACE-Step tree, `use_mlx_dit=True`, `backend=mlx` | Vendor AudioBox ranks **XL** above the 2B line. This screen exists to see whether the drop is audible | Weights **Vendor**. 20.75 GB **User** (different config) |
| 2 | same 2B turbo, `ACESTEP_INIT_LLM` off | 8 steps, no planner | Smaller than rank 1 by the 0.6B LM. Lyrics and structure get worse; prompt 2 is the check | — | MIT | same, skip `LLMHandler.initialize` | Vendor: LM off is the ≤6 GB tier and loses planning | **Vendor** |
| 3 | HeartMuLa-3B via `Acelogic/heartlib-mlx` @ `02dd2e2` | bf16 | Porter table: **~11 GB** for 1 min, **~15 GB** for 5 min, on an M2 Max 32 GB (load 0.82 s, 50 frames / 4 s of audio in 13.4 s total) | far from realtime (0.30× in that 50-frame test) | Apache-2.0 | `heartlib-mlx` | Porter says quality comparable to Suno. The overhaul note's AudioBox figures put HeartMuLa under ACE-Step XL. No 2026-10/11 user RSS found. Last commit **2026-01-21** | **Vendor**, and the port is stale |
| reject | `acestep-v15-xl-turbo` 4-bit re-quant, YuE2, MiniMax-Music3 8-bit | — | XL is the incumbent. A new 4-bit XL with no published Mac RSS is not a candidate. YuE2 is CC-BY-NC and no MLX one-shot was verified. MiniMax is the previous, heavier engine | — | — | — | — | — |

`mlx-community/ACE-Step1.5-MLX-4bit` (card updated 2026-04-14) is a **2.2 GB** 4-bit decoder for the older mlx-audio loader, not a drop-in for `AceStepHandler`. Leave it out unless rank 1 still pins free memory near 22%.

### Music commands

Rank 1 uses the tree already installed for Portal. It does not start the MCP and does not change `MUSIC_ACE_DIT` in the environment of launchd. Pull only the 0.6B planner if `checkpoints/acestep-5Hz-lm-0.6B` is absent:

```bash
# from the ACE-Step checkout that already holds the weights
cd "${HOME}/.portal5/music/ACE-Step-1.5"
uv run python -m acestep.model_downloader --model acestep-5Hz-lm-0.6B
```

If that flag is rejected, the README's manual path is `hf download ACE-Step/acestep-5Hz-lm-0.6B` into `checkpoints/acestep-5Hz-lm-0.6B`. Confirm the directory name with `ls checkpoints` before generating.

One-shot (prompt 1). Repeat with the other two captions and the prompt-2 lyrics. Rank 2 is the same script with `LOAD_LM = False`.

```bash
cd "${HOME}/.portal5/music/ACE-Step-1.5"
/usr/bin/time -l uv run python - <<'PY'
import os
from pathlib import Path
os.environ.setdefault("MUSIC_ACE_ROOT", str(Path.home() / ".portal5/music/ACE-Step-1.5"))
from acestep.handler import AceStepHandler
from acestep.inference import GenerationConfig, GenerationParams, generate_music
from acestep.llm_inference import LLMHandler

root = Path(os.environ["MUSIC_ACE_ROOT"])
out = Path("/tmp/media-variant-screen/music")
out.mkdir(parents=True, exist_ok=True)
DIT = "acestep-v15-turbo"          # rank 1. Incumbent re-run: acestep-v15-xl-turbo
LM = "acestep-5Hz-lm-0.6B"          # incumbent re-run: acestep-5Hz-lm-1.7B
LOAD_LM = True
dit = AceStepHandler()
status, ok = dit.initialize_service(
    project_root=str(root), config_path=DIT, device="auto",
    use_mlx_dit=True, offload_to_cpu=True,
)
if not ok:
    raise SystemExit(f"init failed: {status}")
lm = LLMHandler()
if LOAD_LM:
    lm.initialize(checkpoint_dir=str(root / "checkpoints"), lm_model_path=LM, backend="mlx", device="auto")
params = GenerationParams(
    task_type="text2music",
    caption="sparse acoustic guitar and soft brushed snare, 72 bpm, A minor, no vocals",
    lyrics="",
    duration=30.0,
    inference_steps=8,
    seed=42,
    shift=3.0,
    instrumental=True,
)
config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[42], audio_format="wav")
result = generate_music(dit, lm, params, config, save_dir=str(out))
print("success", getattr(result, "success", None), getattr(result, "audios", None))
PY
```

HeartMuLa only if rank 1's free % is still near 22% **and** the operator rejects the 2B audio. Follow `https://github.com/Acelogic/heartlib-mlx` at `02dd2e22f6a1` (`uv sync`, then their README download into `./ckpt`). The porter's generate entry is that repo's CLI (`--duration` in seconds). Record RSS. Do not treat the ~11 GB table as this host's number.

**Pass:** free % stays well above the incumbent's 22% on the same resident-LLM background, RSS is lower than the XL+1.7B re-run, and the operator accepts prompts 1–3 (prompt 3 must stay a solo guitar). **Fail:** free % still collapses, prompt 2 has no intelligible vocal, or prompt 3 grows a kit.

---

## Screen order

1. Re-measure the three incumbents at the fixed canvas. That is the bar.
2. Image rank 1 (Iris q8), then rank 2, then rank 3. Stop the image lane when one candidate is both smaller and not worse.
3. Video rank 1, then rank 2, at 512×320×97. Keep LTX-2.5 q4 as the audio model unless a silent clip is explicitly enough.
4. Music rank 1, then rank 2. HeartMuLa last.
5. Write the RSS, free %, time, and the look/listen note next to each row. A missing note means the row did not run.

Do not enable modules, edit `config/portal.yaml`, or restart launchd from this plan. A winner is an orchestrator decision after the listen/look.

## RESULT

- **Image:** screen **Iris-3B Turbo q8** first. Porter peak while generating is 5.3 GB at 1024² against a 9 GB incumbent, 4 steps, Apache-2.0. Fallback in the same family is **FLUX.2 klein 4B `-q 4 --small-text-encoder`**. FLUX 3 Klein is a quality model whose published 1024² peaks are not under 9 GB, so it is not in the pull list.
- **Video:** nothing newer than LTX-2.5 q4 is both smaller **and** has audio. Screen **FastMetal-1.3B-QAD** (published 3.87 GiB, silent, Apache-2.0) as a draft engine; keep **LTX-2.5 q4** when the clip needs sound. No MLX q3 of LTX-2.5 exists.
- **Music:** screen **2B `acestep-v15-turbo` + 0.6B LM** on the MLX backend already in `music_worker.py`, against XL + 1.7B. The weight table says this is the cut; the only recent Mac user number (20.75 GB, DiT-only, 48 GB machine) says the RSS still has to be read here.

## SOURCES

- mflux `014252f` READMEs for FLUX.2 (`--small-text-encoder`, decode peaks), Iris (q8/q4 table), FLUX 3 (q4/q6/q8 table), Qwen-Image-2.1 (46 GB bf16 note, turbo flags). https://github.com/mflux-community/mflux fetched 2026-11-19. PyPI `mflux` 0.24.0 is behind that pin.
- teamday.ai, "Best Local Image Generation Models (Nov 2026)", published 2026-11-13, measured 2026-10-25 on an M6 Mac mini 32 GB, mflux 0.23, 4-bit. https://www.teamday.ai/blog/best-local-image-generation-models-2026
- ModelFit FLUX 3 page, published 2026-10-24, citing an mflux 4-bit run on M1 Max 32 GB dated 2026-10-20 (512², 6.7 GB / 4.0 GB low-ram). https://modelfit.io/image/flux-3-klein/
- @aijoey, 2026-10-10, Qwen-Image-2.1 Turbo MLX quants on a 24 GB M4. https://x.com/aijoey/status/2108776632433459426
- @shermstudio, 2026-11-12, Z-Image-Turbo 9 steps at 1536×640, ~26 GB. https://x.com/shermstudio/status/2120855962080677997
- VisualInference, flux3-mlx model card (8-bit 14.3 / 11.0 GB, M4 Pro 48 GB; 4-bit rejected). https://huggingface.co/VisualInference/FLUX-3-Image-Klein-MLX-8bit and https://github.com/felix-ab/flux3-mlx
- devin-lai, flux-3-image-klein-mlx, M5 32 GiB process-footprint table (Q8 7.46 GiB, Q4 5.53 GiB, LPIPS vs FP32). https://github.com/devin-lai/flux-3-image-klein-mlx
- BFL, FLUX 3 Image Klein, 2026-10-15. GPU VRAM only, not a Mac RSS. https://bfl.ai/blog/flux-3-image-klein
- ltx-2-mlx README and `v0.18.0` (2026-10-22), pin `747b30e` (2026-11-01). https://github.com/dgrauet/ltx-2-mlx
- Hao AI Lab, FastMetal-QAD, 2026-08-10 (1.3B 3.87 GiB, 5B 9.34 GiB, M4 Max 36 GB). https://haoailab.com/blogs/fastmetal/ — code pin `c938a8a` 2026-11-15.
- rotecodefraktion, 2026-10-10, unquantized Wan2.2-TI2V-5B mlx-video, M3 Max 64 GB, peak 56.4 GB. https://www.rotecodefraktion.de/en/blog/lokale-ki-video-wan-mac/
- @Hoagie78Ai, 2026-11-15 and 2026-11-19, LTX-2.5 MLX on M1 Max 64 GB, ~27 min / 12 s clip. Time only.
- @cutetoxicguy, 2026-11-15, relaying Phosphene 5.0.20–5.0.25 memory notes. Developer claim, closed app. https://x.com/cutetoxicguy/status/2121875860617879936
- ACE-Step-1.5 README model-choice table and `ca1e85f`. https://github.com/ace-step/ACE-Step-1.5
- 原野, 2026-11-14, 48 GB Mac, ACE-Step load 20.75 GB, DiT-only. https://note.com/fukuoka_ai_c/n/n1c501db0d2d6
- Acelogic/heartlib-mlx README memory table, commit `02dd2e2` dated 2026-01-21. https://github.com/Acelogic/heartlib-mlx

## UNPROVEN

- Every candidate peak on **this** 64 GB host, at the fixed canvas, with oMLX and Ollama resident.
- Whether Iris q8 or klein-4B q4 + small text encoder looks as good as the incumbent klein 4B q8. Porter PSNR is against their own bf16, not against FLUX.2.
- Whether FLUX 3's post-strip-VAE mflux peak (the README says the 18.5/22.8 GB figures are stale) is under 9 GB. Not pulled, because the later teamday 4-bit 1024² figure is still 10.9–11.9 GiB and the run is slower.
- Whether FastMetal at 512×320×97 stays near its 480p/720p published peaks, and whether `--height/--width/--num-frames` on `mlx_wan22_generate.py` match the help text at pin `c938a8a`.
- Whether Phosphene's 5.7 GB path exists in ltx-2-mlx `747b30e`. The README does not state it.
- Process RSS of XL+1.7B vs 2B+0.6B on this host. Free-memory 22% was a system figure.
- HeartMuLa quality against ACE-Step on these three prompts, and its RSS in 2026. The MLX port has not moved since 2026-01-21.
- The look/listen questions in the bullets above are answered, where a run landed, in the judged-results section. HeartMuLa still has no clip.

## Judged results — 2026-11-20

Independent look and listen of the finished screen files. No seat, `config/portal.yaml`, or other production config was changed.

| Medium | Recommendation | Why |
|---|---|---|
| Image | **Keep** `klein4b-q8` | Both judges prefer it on the watch and the fox. Prompt 1 splits on the sign. Iris is smaller after its first prompt, and that does not offset the two losses. The 4-bit klein is the same RSS on this host. Z-Image is slower and sits at a ~45% free floor. |
| Video | **Keep** `ltx25-q4` | All 6 pairs, all three judges. FastMetal is silent on prompts that ask for sound, and it also loses the picture. LTX's door clip shuts or barely opens; it still wins the pair. |
| Music | **Need more evidence** | XL-Turbo wins the vocal prompt on both Gemini listeners, and the 0.6B-LM turbo fails the solo-guitar prompt by adding drums and bass. The no-LM turbo wins the solo guitar and drops the verse. XL-Turbo's 7–8% free floor and +28–38 GB swap is a UX veto against treating that win as a reason to stay. No candidate clears all three prompts. |

### How the files were judged

Blind A/B, one incumbent clip against one candidate clip, order drawn with seed `20261120`. Prompts named the picture, the soundtrack, or the music. They did not name a checkpoint. Scores are 1–5. Cleanliness 5 means intact geometry, text, or audio. The tables below are unblinded after scoring. Order is candidate then incumbent.

Listeners and viewers:

- **Gemini 4 Neon** (`gemini-4-neon-high` through the Antigravity CLI). Saw the PNGs, watched the mp4s, and listened to the wavs.
- **Gemini 4 Hydrogen** (`gemini-4-hydrogen-high`, same Google lineage). Listened to the music and watched the video. On vid11, vid12, vid14, and vid15 the first prompt returned `cannot_perceive`; those four were re-scored from re-encoded mp4s with the refusal sentence removed. vid10 and vid13 were scored from the original mp4s.
- **Claude Opus** (Claude Code `--model opus`, Anthropic). Read the PNGs. For video it saw one middle frame plus a 7-frame strip in time order. It cannot hear, so it has no audio score and no music score.
- **Grok Voice Transcribe 2.0** (`grok-voice-transcribe-2.0`, xAI STT). Speech text only. An empty transcript on waves, squeaks, footsteps, or an instrumental is not a musicality score.

Added after these scores were taken (2026-11-20), so it did not score the original run:
**Xiaomi MiMo v2.6 Pro** (`mimo-v2.6-pro`, Xiaomi direct) is wired as the music judge step's
non-Google audio lineage — see "Second listener and HeartMuLa's state" below.

Image and video therefore have two lineages (Gemini and Claude). Music's two full listeners are both Gemini 4. The xAI transcript is a second lineage for whether words are present.

The worker session (Grok) looked at the four prompt-1 bakery PNGs after the scores, with the filenames visible, to check the sign dispute. That look is not a blinded third score.

Measurements are the screen's own tables: `image-20261120T055910Z`, `video-20261120T061117Z` (FastMetal), `video-20261120T142117Z` (LTX-2.5 q4, the incumbent re-run that produced mp4s), `music-20261120T134823Z`.

### Image

Incumbent `klein4b-q8`: 28.6–34.7 s, peak RSS 7.52–7.54 GB, free floor 73–74%, swap 0. Iris q8: 196.5 s then 25.6 s and 22.6 s, peak RSS 6.89 then 4.16–4.35 GB, free floor 76–78%, swap 0. Klein q4 + small text encoder: 55.6 / 26.6 / 25.5 s, peak RSS 8.10 then 7.52 GB, free floor 80–81%, swap 0. Z-Image q4: 91.4–96.1 s, peak RSS 11.57–13.13 GB, free floor 45–47%, swap 0.

Scores are adherence / fidelity / cleanliness.

| Pair | Judge | Candidate | Incumbent | Winner |
|---|---|---|---|---|
| iris p1 | Neon | 4/3/4 | 5/5/4 | incumbent |
| iris p1 | Claude | 5/4/4 | 4/5/3 | candidate |
| iris p2 | Neon | 3/3/2 | 5/5/3 | incumbent |
| iris p2 | Claude | 3/3/3 | 5/4/4 | incumbent |
| iris p3 | Neon | 4/3/3 | 5/5/4 | incumbent |
| iris p3 | Claude | 4/3/3 | 5/5/4 | incumbent |
| q4 p1 | Neon | 4/4/3 | 5/5/4 | incumbent |
| q4 p1 | Claude | 4/4/4 | 4/4/3 | candidate |
| q4 p2 | Neon | 3/3/2 | 5/4/3 | incumbent |
| q4 p2 | Claude | 4/4/2 | 4/4/4 | incumbent |
| q4 p3 | Neon | 5/5/5 | 5/4/4 | candidate |
| q4 p3 | Claude | 5/4/4 | 5/5/4 | incumbent |
| zimage p1 | Neon | 3/5/4 | 4/4/3 | candidate |
| zimage p1 | Claude | 3/4/4 | 4/4/3 | incumbent |
| zimage p2 | Neon | 3/3/2 | 5/4/3 | incumbent |
| zimage p2 | Claude | 4/4/3 | 5/4/3 | incumbent |
| zimage p3 | Neon | 3/4/5 | 5/4/4 | incumbent |
| zimage p3 | Claude | 3/4/4 | 5/5/5 | incumbent |

Agreement: 5 of 9 pairs share a winner, and every shared winner is the incumbent. The four splits are prompt 1 for Iris, q4, and Z-Image, plus the q4 fox.

Prompt 1 is a real split, and the pixels match the written reasons. The incumbent sign reads PORTAL 5 on one face and PORTAL on the other. Iris, q4, and Z-Image each show one PORTAL 5. Claude weights that text. Neon weights the incumbent's wetter street and busier bakery interior, and calls the Iris interior synthetic. Claude calls the Z-Image interior a homeware shop more than a bakery. The q4 fox is the other split: Neon calls its fur and paws clearer; Claude calls the incumbent's rim light and pine bokeh stronger.

Watch, both judges, every candidate: the incumbent is the coherent polished-steel watch on black. Iris puts a softbox in frame and garbles the bracelet. The q4 case loses the strap and sprouts extra crowns. Z-Image puts a softbox in the black field and reads as brushed metal.

Fox, Iris and Z-Image, both judges: the incumbent has the closed eye, golden-hour rim, and fur. Iris is flatter, with an awkward paw. Z-Image's fox is not fully asleep.

Keep `klein4b-q8`. Iris is the only candidate with a better footprint after the cold first prompt, and it loses the watch and the fox on both lineages.

### Video

Incumbent re-run `video-20261120T142117Z`, `ltx25-q4`, 512×320, 97 frames, audio stream present: 88.9–94.3 s, peak RSS 10.92–13.51 GB, free floor 81–84%, swap 0. FastMetal from `video-20261120T061117Z`, no audio stream. 1.3B: 61.2–88.9 s, peak RSS 17.50–19.60 GB, free floor 27–38%, swap 0. 5B: 41.9–47.0 s, peak RSS 13.57–20.89 GB, free floor 63–69%, swap 0.

Gemini scores are adherence / fidelity / cleanliness / temporal / audio. Claude has no audio number. FastMetal audio is 1 on every Gemini score because the file is silent.

| Pair | Judge | Candidate | Incumbent | Winner |
|---|---|---|---|---|
| 1.3B waves | Neon | 3/3/4/4/1 | 5/5/5/5/5 | incumbent |
| 1.3B waves | Hydrogen | 3/3/3/3/1 | 4/5/5/5/1 | incumbent |
| 1.3B waves | Claude | 3/2/2/3 | 5/4/4/4 | incumbent |
| 1.3B door | Neon | 1/2/2/2/1 | 3/4/4/3/3 | incumbent |
| 1.3B door | Hydrogen | 2/2/2/2/1 | 3/3/4/3/3 | incumbent |
| 1.3B door | Claude | 2/3/3/3 | 3/4/4/3 | incumbent |
| 1.3B walk | Neon | 2/2/3/2/1 | 5/4/5/5/5 | incumbent |
| 1.3B walk | Hydrogen | 2/3/2/2/1 | 5/4/5/5/5 | incumbent |
| 1.3B walk | Claude | 2/2/2/3 | 4/4/4/4 | incumbent |
| 5B waves | Neon | 2/1/1/2/1 | 5/5/5/5/5 | incumbent |
| 5B waves | Hydrogen | 3/2/2/2/1 | 5/5/5/5/5 | incumbent |
| 5B waves | Claude | 3/3/1/2 | 5/4/4/4 | incumbent |
| 5B door | Neon | 1/2/3/2/1 | 3/4/4/3/4 | incumbent |
| 5B door | Hydrogen | 1/3/3/2/1 | 3/3/4/3/3 | incumbent |
| 5B door | Claude | 1/3/3/3 | 2/3/4/3 | incumbent |
| 5B walk | Neon | 2/2/2/2/1 | 4/4/4/5/5 | incumbent |
| 5B walk | Hydrogen | 2/2/2/2/1 | 5/5/5/5/5 | incumbent |
| 5B walk | Claude | 1/2/2/2 | 5/4/4/4 | incumbent |

Agreement: 6 of 6 pairs, three judges, incumbent. FastMetal 1.3B's walk is legs in place, facing away. FastMetal 5B's door is a latch close-up, and its waves pick up a blue rectangle (Claude and Hydrogen). LTX's ocean and walk match the prompt, including footsteps and wave sound on both Gemini listeners.

The door prompt is the weak LTX clip. Neon and Hydrogen both say the door shuts or slams instead of opening toward the camera, with a squeak present. Claude sees a heavy door and a light shaft, and little opening. FastMetal does not open a heavy door either, and it is silent. LTX still wins a weak pair.

Audio disagreement, waves only: Neon scores LTX audio 5 (waves and wind, no music). Hydrogen scores it 1 (unwanted music) and still picks LTX on the picture. xAI STT returned no words on any LTX track, which neither confirms nor rules out music under the waves. The winner does not move.

Keep `ltx25-q4`. Silence is a failed soundtrack, and the silent clips are also the weaker pictures. Their RSS is higher than LTX on this canvas.

### Music

`music-20261120T134823Z`. XL-Turbo + 1.7B LM: 223–230 s, process RSS 5.17–5.80 GB, free floor 7–8%, swap +27.94 to +37.92 GB. Turbo 2B + 0.6B LM: 42.3–57.5 s, RSS 11.22–13.59 GB, free floor 24–47%, swap about 0 to +1.04 GB. Turbo 2B with the LM off: 17.8–21.1 s, RSS 10.74–12.28 GB, free floor 27–42%, swap 0 to +0.84 GB.

Scores are adherence / musicality / instruments / cleanliness / vocals. Both listeners are Gemini 4.

| Pair | Judge | Candidate | Incumbent | Winner |
|---|---|---|---|---|
| 0.6B LM, guitar+snare | Neon | 4/4/4/5/5 | 5/5/5/5/5 | incumbent |
| 0.6B LM, guitar+snare | Hydrogen | 4/4/4/5/5 | 2/4/3/5/1 | candidate |
| 0.6B LM, vocal | Neon | 3/3/4/4/4 | 5/5/5/5/5 | incumbent |
| 0.6B LM, vocal | Hydrogen | 2/3/3/4/3 | 5/4/5/5/5 | incumbent |
| 0.6B LM, solo nylon | Neon | 1/2/1/4/5 | 5/4/5/5/5 | incumbent |
| 0.6B LM, solo nylon | Hydrogen | 1/3/1/5/5 | 4/3/4/5/5 | incumbent |
| no LM, guitar+snare | Neon | 4/3/3/5/5 | 5/5/4/5/5 | incumbent |
| no LM, guitar+snare | Hydrogen | 4/4/3/5/5 | 3/4/2/4/2 | candidate |
| no LM, vocal | Neon | 2/3/3/4/4 | 5/5/5/5/5 | incumbent |
| no LM, vocal | Hydrogen | 3/4/4/5/4 | 5/5/5/5/5 | incumbent |
| no LM, solo nylon | Neon | 5/5/5/5/5 | 4/3/4/4/5 | candidate |
| no LM, solo nylon | Hydrogen | 5/5/5/5/5 | 3/2/3/4/5 | candidate |

Agreement: 4 of 6 pairs. The splits are both copies of prompt 1. Hydrogen hears humming on XL-Turbo there (vocals 1 and 2) and picks the candidate. Neon hears no singer, a brushed snare, and about 72 bpm, and picks XL-Turbo. xAI STT returned no words on any prompt-1 or prompt-3 clip, so it does not confirm the humming.

Prompt 2, both listeners, both candidates: XL-Turbo sings the verse and the chorus. The 0.6B-LM turbo starts like a slow ballad, repeats a chorus line, and drops "than the night". The no-LM turbo drops the verse. xAI STT agrees on the shape of that gap. XL-Turbo: "Streetlight on the west stop, I am walking home alone. Hold the line, hold the light, we are louder than the night." (the second pairing repeats "hold the line" and still has the verse). 0.6B LM: "Streetlight on the window, I am walking home. Hold the light, hold the light, hold the light, we are louder." No-LM: "Hold the line, hold the line, we are louder than the night." "West stop" and "window" are mishearings of "wet stone". The words are intelligible on all three; the candidates are missing lines.

Prompt 3: both listeners say the 0.6B-LM turbo adds drums and bass, which is a miss. Both say the no-LM turbo is the better solo nylon guitar, and that XL-Turbo's take is simpler block chords.

Need more evidence before a seat change. The 0.6B-LM turbo fails the solo-guitar constraint. The no-LM turbo fails the verse. XL-Turbo is the better vocal and the one that swaps the host to a 7–8% free floor, which is a UX veto against keeping it on sound alone. A later candidate has to clear the vocal and the solo guitar without that swap. HeartMuLa was not in this run.

### Second listener and HeartMuLa's state — 2026-11-20, after the judgments

Music's two full listeners were both Gemini 4. `scripts/proofs/media_screen_listen.py` is now
the screen's judge step for a non-Google lineage: it pairs each candidate clip against the
incumbent for the same fixed prompt, draws the A/B order blind from seed `20261120`, asks an
audio-capable model for the same five 1–5 dimensions plus the words it actually heard, and
writes `listen_<listener>_music_<date>.md` and `listen_rows.jsonl` beside the judge sheet.
`--medium music --listen mimo-v2.6-pro` runs it at the end of a screen.

Chosen listener: **Xiaomi MiMo v2.6 Pro** (`mimo-v2.6-pro`, Xiaomi direct API,
`https://api.xiaomimimo.com/v1`). Each call returns `audio_tokens`, so ingestion is proven per
call rather than inferred. It transcribes "Streetlight on the wet stone" — where both Gemini
listeners heard "west stop"/"window" — and hears the second "Hold the line" repeat. The same
model behind OpenRouter (routed to DeepInfra) invented a female vocal on the solo-guitar clip,
so this listener pins the endpoint. Runner-up, selectable with `--listener
qwen/qwen3.8-omni-flash --base-url https://openrouter.ai/api/v1`, is accurate on the element
checklist but looser on lyric text. The model survey, the `CANNOT_PERCEIVE` results and the
smoke transcripts are in `coding_task/FINDING_MUSIC_SECOND_LISTENER.md`.

HeartMuLa is **not installed** on this host: no `ckpt/`, no `ckpt-mlx/`, no weights under
`~/.portal5` or `/Volumes/data01`, and nothing audio-capable in `ollama list`. Its MLX port is
cloned at `coding_task/scratch/heartlib-mlx` but unbuilt. Installing it is `uv sync`, the
`HeartMuLa-oss-3B` + `HeartCodec-oss` Hugging Face downloads into `./ckpt`,
`python -m heartlib_mlx.utils.convert --src ./ckpt --dst ./ckpt-mlx`, and then a
`kind: heartlib` catalog row. Until that runs, HeartMuLa has no clip and no row.

## Operator verdicts (2026-11-20)

The operator's own look and listen of the same files, made after the model judges' scores above. These are the decisions, and they decide the seats. **No seat and no config changed:** image stays `flux2-klein-4b` at `-q 8` (`portal/modules/media/tools/mflux_mcp.py`), video stays `ltx-2-mlx` on `dgrauet/ltx-2.5-mlx-q4` (`portal/modules/media/tools/video_mlx_mcp.py`), music stays `acestep-v15-xl-turbo` + `acestep-5Hz-lm-1.7B` (`portal/modules/media/tools/music_worker.py`). Clip paths are under `${AI_OUTPUT_DIR}/generated/screens/`; run names are the ones in the judged-results section.

| Medium | Operator verdict | Model judges | Agreement |
|---|---|---|---|
| Image | **Keep `klein4b-q8`** | Keep `klein4b-q8` | Agrees, after a reversed first pick |
| Music | **Keep XL-Turbo**; `ace-turbo2b-nolm` is the strong lighter alternative | Need more evidence | Operator decided where the judges stopped |
| Video | **Keep `ltx25-q4`**; every candidate is bad | Keep `ltx25-q4`, unanimous | Agrees on the seat, harsher on the incumbent |

### Image — keep `klein4b-q8`

The operator's first pick was `zimage-q4`, the rank-3 row of `image-20261120T055910Z`. On re-review the operator agreed with the judges that the incumbent `klein4b-q8` is better, so `zimage-q4` is the runner-up rather than the pick. That first pick is also the row the judges put behind the incumbent: both lineages preferred the incumbent on two prompts of three, and prompt 1 was their only split. The operator's re-review therefore moved the image verdict onto the judges' pick, and it stayed there.

The footprint does not move that verdict. `zimage-q4` measured 11.57–13.13 GB peak RSS and a 45–47% free floor against the incumbent's 7.52–7.54 GB and 73–74%, on the same three prompts.

### Music — keep XL-Turbo, with `ace-turbo2b-nolm` as the lighter alternative

The operator's best overall clip is `0ba3933b-08df-0687-7290-23326db8b9a1.wav`, which is `ace-xl17-p1` in `music-20261120T061706Z` (XL-Turbo + 1.7B LM, fixed prompt 1). Two more clips are winners on their prompt: `3be21b4b-ca7b-b5f7-1848-c5a0e223598d.wav` (`ace-xl17-p2`, the vocal prompt, run `music-20261120T134823Z`) and `aab2f47b-735c-b8b4-6260-10a9b28e863d.wav` (`ace-turbo2b-nolm-p2`, the same run, the 2B turbo with the LM off).

Those winners track the judged rows: XL-Turbo on prompt 2 and the no-LM turbo on prompt 3 were already the winners for both Gemini listeners and for MiMo, and prompt 1 was the one pair the listeners split. Where the operator differs is the overall call — the judges stopped at "need more evidence" and the operator keeps the incumbent.

`ace-turbo2b-nolm` is recorded as the **strong lighter alternative**. It won the solo-nylon prompt for both Gemini listeners and for the MiMo second listener — the one prompt XL-Turbo loses on sound — and it ran in 17.8–21.1 s at 10.74–12.28 GB RSS with swap at 0 to +0.84 GB. XL-Turbo's cost is what makes the lighter arm more than a footnote: 223–230 s, process RSS 5.17–5.80 GB, free floor **7–8%**, swap **+27.94 to +37.92 GB**. The operator keeps XL-Turbo, with that cost on the record.

XL-Turbo keeps the seat on the evidence the judges recorded rather than on memory: it is the only arm that sang the verse and the chorus. The operator named no `ace-turbo2b-lm06` clip among the winners, which matches both Gemini listeners (drums and bass on the solo-guitar prompt). A later candidate has to clear the vocal and the solo guitar without the swap.

"Best overall" is a property of that **take**, not of the arm: `music-20261120T061706Z` holds only the prompt-1 XL-Turbo wav and no measured row, and that wav is a second, distinct take of the same spec and seed 42 (same 30.0 s, different sha256, waveform correlation 0.11) from the `8e1de78e-…wav` that `music-20261120T134823Z` produced and the judges scored.

### Video — keep `ltx25-q4`

Every candidate in the screen is bad, in the operator's judgement. The best of them are the incumbent's own re-runs, `ltx25-q4-p2.mp4` (door) and `ltx25-q4-p3.mp4` (walk) in `video-20261120T142117Z`; the waves clip `ltx25-q4-p1.mp4` is not among them. The seat stays on `ltx25-q4`. The FastMetal arms are rejected: silent on prompts that ask for sound, and the weaker picture even when the soundtrack is ignored.

That agrees with the judges' unanimous incumbent win and goes further. The door clip the judges call the weak LTX row is one of the operator's two best; the seat survives because the incumbent is the least bad file in the screen, not because it is good.
