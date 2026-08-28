---
id: unit-p5-roadmap-p5-fut-speech-002-speech-model-shootout
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-SPEECH-002: Speech-Model Shootout"
sources:
- type: code
  path: scripts/mlx-transcribe.py
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: CHANGELOG.md
- type: code
  path: tests/benchmarks/bench_tps.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5934029
updated_at: 1787936110.0
---

P5-FUT-SPEECH-002 is planned work. The current production speech stack is
`scripts/mlx-transcribe.py` — Parakeet-TDT-v3 for the transcript plus Sortformer
(`mlx-community/diar_sortformer_4spk-v1-fp32`) speaker diarization merged at the
word level, American English only, serving on port 8924 — and
`scripts/mlx-speech.py` (`mlx-community/Kokoro-82M-bf16` plus three Qwen3-TTS
12Hz-1.7B variants for custom-voice, voice-design, and base/cloning, and Qwen3-ASR
for plain STT, serving on port 8918). The three bench-only speech candidates from
TASK_MODEL_REFRESH_V7 — Voxtral-Mini-4B-Realtime-2602, Voxtral-4B-TTS-2603, and
Granite-Speech-4.1-2B — are recorded in `CHANGELOG.md` but are not registered in
`config/portal.yaml`. The planned shootout would score WER, keyword F1, TTFT, and
subjective Likert ratings and emit a Pareto frontier for the speech lane.
`tests/benchmarks/bench_tps.py` is a text TPS harness and would not exercise
streaming ASR or TTS rendering.

## Why

Speech evaluation cannot reuse the text benchmark because the artifacts are
audio: WER and keyword F1 need a shared audio corpus, TTFT measures first audio
chunk rather than first token, and TTS has no transcript to score. The bench
candidates are kept out of the serving fleet until the shootout runs, so
`config/portal.yaml`, which defines the fleet, registers only the production
speech servers and the roadmap keeps the candidates out of routing.
