# FINDING — music screen: a second, non-Gemini listener, and HeartMuLa's install state

**Date:** 2026-11-20 · **Lane:** `lane/music-second-listener` · **Brief:** `coding_task/BRIEF_MUSIC_SECOND_LISTENER.md`

The 11-20 media screen left music at "need more evidence" partly because the only two
listeners that can hear audio are both Gemini 4, and HeartMuLa was not in the run. This
finding records what was measured here: which model actually ingests a wav, the smoke that
proves it, and what HeartMuLa would need before it can be a row.

## 1. Which models can hear a wav

`opencode models` lists the providers this machine can reach. OpenRouter publishes input
modalities per model, so the audio-capable set was read from that rather than guessed
(`GET https://openrouter.ai/api/v1/models`, 477 models, input modalities including `audio`,
fetched 2026-11-20). Non-Google entries:

| Model | ctx | OpenRouter route | Smoke result on a real screen clip |
|---|---|---|---|
| `xiaomi/mimo-v2.6-pro` | 1.05M | Xiaomi (direct too) | hears the clip; near-verbatim lyrics; accurate element checklist |
| `qwen/qwen3.8-omni-flash` | 1.0M | Alibaba | hears the clip; accurate element checklist; looser lyric text |
| `thinkingmachines/inkling` | 524K | Thinking Machines | hears it, but only "acoustic guitar / ~70 BPM" — thin detail |
| `meta/muse-ember` (and `muse-wonder`, `muse-spark-open`) | 1.05M | Meta | `CANNOT_PERCEIVE` on a 30 s wav |
| `openai/gpt-audio` | 128K | OpenAI | billed 300 audio tokens, answered `CANNOT_PERCEIVE` |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | 256K | NVIDIA | `CANNOT_PERCEIVE` |
| `mistralai/voxtral-small-24b-2507` | 32K | Mistral | HTTP 429 in the smoke window; speech-first model, not retried |
| `perceptron/perceptron-mk1.5` | 36K | Perceptron | not tried |

Reachable but unusable for this job: **codex** (OpenAI CLI, text/vision only), **grok**
(`grok-voice-transcribe-2.0` is STT — the 11-20 run already showed it returns no words on
instrumentals, which is not a musicality score). **Local oMLX/Ollama**: the installed set has
no audio-input checkpoint (`ollama list`, `/Volumes/data01/omlx-models` — all text or vision);
`qwen3-vl:32b` is vision. A local omni model would have to be pulled first.

## 2. The smoke — the same clip, five questions

Clip: `~/AI_Output/generated/screens/music-20261120T134823Z/ace_run/ace-xl17-p2/3be21b4b-…wav`
(30.0 s, 48 kHz stereo, the XL-Turbo take of fixed prompt 2 — the vocal prompt). Question:
transcribe sung words verbatim, name instruments, tempo, vocals, mix; `CANNOT_PERCEIVE` if deaf.

`xiaomi/mimo-v2.6-pro`, direct (`https://api.xiaomimimo.com/v1/chat/completions`):

```
LYRICS: Street light on the wet stone / I am walking home alone / Hold the line / Hold the line / We are louder than the night
INSTRUMENTS: Electric guitar, bass guitar, drums
TEMPO: Upbeat, ~115 BPM
VOCALS: Female, clear, melodic
MIX: Clean, balanced, punchy, modern pop/disco
audio_tokens 188
```

That is the clip's actual lyric sheet, including the second "Hold the line" repeat that the
11-20 run recorded and the "wet stone" both Gemini listeners misheard as "west stop"/"window".
`audio_tokens: 188` is the provider's own count of the audio it ingested — the request was not
text-only.

The same model behind OpenRouter (routed to DeepInfra) heard the same clip as
`"Street light on the west side …"` and, on the solo-nylon clip, invented a female vocal. So
**the endpoint matters**: the listener must be pinned to the Xiaomi direct API, not whatever
OpenRouter routes to.

Controls (same 30 s canvas):

- xl-p3 (solo nylon, no vocals): `LYRICS: NONE … Acoustic guitar … VOCALS: None` — correct.
- nolm-p2 (2B no-LM, verse dropped): `Hold the light, hold the light, we are louder than the night`
  — correct: it hears the missing verse.
- lm06-p3 (0.6B-LM, the clip both Gemini listeners call "adds drums and bass"):
  checklist probe → `kick NO / snare NO / hi-hat-shaker YES 2 / bass YES 3 / acoustic guitar YES 3`.
- xl-p1 (guitar + brushed snare, 72 bpm): `acoustic guitar YES`, `humming/whistling NO` — matches
  Neon, not Hydrogen's "humming".

## 3. Choice

**`xiaomi/mimo-v2.6-pro`, Xiaomi direct API** is the second listener. It is the one the brief
names, it transcribes lyrics accurately enough to settle the verse/chorus question the screen
actually turns on, and it reports audio tokens so ingestion is proven per call. Runner-up is
`qwen/qwen3.8-omni-flash` (equally good on the element checklist, weaker on lyric text); it is
selectable with `--listener qwen/qwen3.8-omni-flash --base-url https://openrouter.ai/api/v1`.

Per-call cost observed: `$0.00025`–`$0.00035`; two clips per paired request.

## 4. HeartMuLa — not installed

Found (not installed):

- `Acelogic/heartlib-mlx` @ `02dd2e2` is **cloned** at `coding_task/scratch/heartlib-mlx`
  (gitignored scratch from an earlier session). No `.venv`, no `ckpt/`, no `ckpt-mlx/`.
- No HeartMuLa weights anywhere on the host: nothing under `~/.portal5`, `/Volumes/data01`,
  and no oMLX/Ollama entry. `ollama list` has no audio/music model; `/Volumes/data01/omlx-models`
  has none.
- `heartlib-mlx`'s `generate.py` resolves checkpoints from `~/Developer/heartlib-mlx/ckpt-mlx`,
  which does not exist on this host.

What it needs, in order (from the repo's own README at pin `02dd2e2`):

```bash
cd coding_task/scratch/heartlib-mlx        # or a permanent home, e.g. ~/.portal5/music/heartlib-mlx
uv sync                                     # mlx>=0.22, numpy, safetensors, tokenizers, soundfile
mkdir -p ckpt
huggingface-cli download HeartMuLa/HeartMuLa-oss-3B --local-dir ckpt/HeartMuLa-oss-3B
huggingface-cli download HeartCodec-oss --local-dir ckpt/HeartCodec-oss   # exact repo id from its README
huggingface-cli download HeartMuLa/HeartMuLa-oss-3B tokenizer.json --local-dir ckpt
python -m heartlib_mlx.utils.convert --src ./ckpt --dst ./ckpt-mlx        # one-off MLX conversion
```

Then a row of `kind: heartlib` in `scripts/proofs/media_screen_catalog.yaml` calling
`generate.py --tags <caption> --lyrics <lyrics> --duration 30 --output {output}`, with the
row's RSS sampled the same way. Weights are ~9–11 GB of download plus the MLX conversion and
~11 GB resident at 1 minute (porter's table, M2 Max 32 GB) — the brief's "if it is not
installed, say what install it needs and stop" is where this stops.

## 5. Judge-step wiring

`scripts/proofs/media_variant_screen.py` measures rows and writes a judge sheet; judging was
manual (Antigravity/Gemini + Claude reading files, per the doc). `scripts/proofs/media_screen_listen.py`
is the judge step now: it pairs each candidate against the incumbent per prompt, draws the A/B
order blind from a seed, asks the listener for the doc's five 1–5 dimensions plus the words it
actually heard, unblinds and writes `listen_<listener>_music_<date>.md` beside the judge sheet
plus `listen_rows.jsonl` receipts. `media_variant_screen.py --medium music --listen mimo-v2.6-pro`
runs it at the end of a screen.

That gives music two lineages: Gemini 4 (Antigravity) and Xiaomi MiMo. Nothing in
`config/portal.yaml` or any seat changed.

## 6. The step run over the 11-20 clips

Run from a **copy** of `music-20261120T134823Z/rows.jsonl` in scratch (the clips resolve by
absolute path; nothing was written into the live screen directory):

`uv run python scripts/proofs/media_screen_listen.py --run-dir coding_task/scratch/judge/run`

| pair | candidate | incumbent | MiMo winner | 11-20 Gemini |
|---|---|---|---|---|
| lm06 p1 | 2/4/2/5/5 | 3/4/3/4/5 | incumbent | split (Neon incumbent, Hydrogen candidate) |
| lm06 p2 | 3/3/4/4/3 | 4/4/5/5/4 | incumbent | incumbent, both |
| lm06 p3 | 2/3/2/4/5 | 5/4/5/5/5 | incumbent | incumbent, both |
| nolm p1 | 5/4/5/5/5 | 4/4/4/4/5 | candidate | split (Neon incumbent, Hydrogen candidate) |
| nolm p2 | 2/3/3/4/4 | 4/4/4/5/4 | incumbent | incumbent, both |
| nolm p3 | 5/5/5/5/5 | 3/3/3/4/5 | candidate | candidate, both |

Four of four pairs where both Gemini listeners agreed come out the same way here; on the two
prompt-1 splits it takes one each. The reasons are the screen's own discriminators, not generic
praise: on lm06 p3 it hears "plucked guitar, shaker percussion … percussion despite no-drums
instruction"; on nolm p2 "chorus only, verse missing"; on p2 it transcribes the incumbent as
"Streetlight on the wet stone … Hold the line, hold the line" and the lm06 take as adding
"hold the light" (the doc's "repeats a chorus line"). Every receipt carries `audio_tokens: 376`.

This is a judge call against real clips, not a live-stack result; the re-screen itself is the
orchestrator's.
