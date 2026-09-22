# Landscape 2026Q3 three-bench spike — closeout (rejected, all three)

**Base:** `e776b3a9` · **Closed:** 2026-09-22 · **Task:** `coding_task/TASK_LANDSCAPE_2026Q3_BENCHES_V1.md`

All three landscape items probed under this task were evaluated and rejected.
Every installed artifact (services, venvs, model checkpoints, config wiring,
bench code, fixtures, output images) has been removed. This is the only
surviving record — treat the findings below as authoritative; the original
per-phase receipts no longer exist in the repo or on disk.

## P1 — Tencent AuK (MLX speech edit/separate/enhance)

**Verdict: not bringing in now.** Real capability, low current need.

- Mechanically worked end to end: install, MCP wiring, 8/8 seat-relevant
  items produced valid output on the first real run.
- Voice cloning against the operator's own registered reference
  (`~/.portal5/voice_profiles/chris/reference.wav`) sounded good once a
  real bug was found and fixed — `synthesize()` was sizing output duration
  off the *reference clip's* length instead of the *text's*, so a 15s
  reference made the model hallucinate ~11s of invented speech for a
  4-word phrase.
- A separate false alarm during review: a sample rated "terrible" turned
  out to be Open WebUI's own mp3 transcode (~32kbps) for chat playback,
  not the underlying wav (confirmed byte-identical to the raw output) —
  worth remembering for any future audio judgment done through the OWUI
  chat player rather than the raw file.
- Spiked the non-distilled `base` variant against `flash` on the same
  sentence; operator rated `flash` (the tested default) slightly better.
- Never fully scored: content-edit, paralinguistic-edit, separation, and
  enhancement (the actual seat-relevant capabilities, as opposed to
  baseline TTS/cloning) were not listened to before the decision to not
  proceed.
- Operator call: capabilities are real (content edit, paralinguistic
  edit, separation, enhancement — none of which the seated Kokoro/
  Qwen3-TTS/Qwen3-ASR stack has), but not a frequent enough need to carry
  the ~50GB disk footprint and a second speech service to maintain right
  now. Revisit if a concrete use case for those specific capabilities
  comes up.

## P2 — Qwen-Image-2.1

**Verdict: not bringing in yet — wait for a more complete mflux release.**

- The task originally probed the wrong model entirely (Qwen-Image-Edit-2509,
  a point update to the already-seated `qwen-image-edit`), caught and
  redone against the actual model the operator asked about
  (`Qwen/Qwen-Image-2.1`).
- mflux 0.19.1 (seated) had no support; upgraded the host-native mflux venv
  to 0.20.0 to get native `mflux-generate-qwen-2.1` support (later reverted
  back to 0.19.1 as part of closeout).
- Base text-to-image generation is genuinely strong — clean, well-composed,
  fast (~70-120s for a 20-step 768px image vs. `qwen-image-edit`'s ~730s
  for a comparable edit).
- Image editing does not work as tested, at either `--image-strength 0.5`
  or `0.8` — prompt-requested changes (sweater color, added text, pose)
  were not applied either time. Root cause found in mflux's own installed
  README (`mflux/models/qwen21/README.md`, Notes section): **"Not yet
  supported: the edit/instruction variant (needs the Qwen3-VL vision
  tower)."** mflux 0.20.0's Qwen-Image-2.1 port is text-to-image only, plus
  a generic latent-noise img2img bolted on "like the other models" — it
  does not implement the actual instruction-following edit mode the model
  card advertises. This was never a fair test of editing; it isn't
  implemented in mflux yet.
- Operator call: revisit once mflux ships the real edit/instruction variant
  (needs the Qwen3-VL vision tower per mflux's own notes) so generation and
  editing can be evaluated as one complete capability, rather than
  half-testing a code path mflux itself flags as unfinished.

## P3 — IBM Granite Switch 4.1-3b (compliance verifier)

**Verdict: no.**

- Original bench (policy-guardrails adapter, hand-written instruction text,
  4000-char truncation) was set up to fail — the row-mismatch gold edges
  aren't about the wrong-standard/boilerplate question that adapter judges;
  fixed in a v2 rerun using the checkpoint's own shipped `io_configs/`
  templates verbatim, the correct adapter (`requirement-check`), and no
  truncation (checkpoint context is 131072 tokens; longest section in the
  183-edge corpus is ~14.5k chars).
- `requirement-check`, even correctly framed, returned the literal constant
  reply `{"score": "no"}` on all 183 edges — checked the raw output, zero
  variance including on clean SUPPORTED edges. Not a usable signal either
  way; needs full document context or a different prompt structure before
  it's worth measuring again.
- `factuality-detection` (checkpoint's verbatim template) gave a real but
  weak result: 26.2% defect catch, 38.3% false-positive rate on SUPPORTED
  edges.
- Same-corpus comparison against the seated Ollama compliance model
  (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k`): 100% defect catch,
  75.2% false-positive rate — genuinely discriminating, just biased toward
  flagging things given only bare-citation context.
- Decisive factor: **Granite Switch was slower per-edge than the seated
  Ollama model despite being 8x smaller** (~2.9s/edge vs. Ollama's 2.05s),
  because it runs unoptimized HuggingFace `transformers` on MPS rather than
  an optimized Metal backend (Ollama's llama.cpp path). Not a speed win on
  this hardware as wired, on top of the accuracy tradeoffs above.
- Operator call: reject. No path to promotion identified without both a
  faster inference backend (MLX port, not raw transformers/MPS) and a
  reworked `requirement-check` prompt — not worth carrying the adapter
  forward on current evidence.

## What was removed

- AuK: launchd service, plist, `~/.portal5/auk/` (venv + repo + checkpoints,
  ~51GB), `config/portal.yaml` mcp_fleet entry, `.env.example` vars,
  CLAUDE.md port reservation, `scripts/lib/services.sh` functions,
  `launch.sh` dispatch/help, `portal/modules/media/tools/auk_mcp.py`, wiki
  fact-units, all bench code/fixtures/results.
- Qwen-Image-2.1: mflux venv reverted to 0.19.1, HF weight cache
  (`Qwen/Qwen-Image-2.1`, ~31GB) removed, all bench code/fixtures/output
  images. No config was ever wired (P2 was env-override only).
- Granite Switch: `~/.portal5/granite-switch/` (venv + checkpoint, ~8.6GB)
  removed. No config was ever wired (bench-only venv per the task's own
  isolation rule — never touched `portal/platform/inference/`).
- `./launch.sh sync-config` re-run after the AuK config revert; confirmed
  idempotent (no diff) against the reverted `config/portal.yaml`.
