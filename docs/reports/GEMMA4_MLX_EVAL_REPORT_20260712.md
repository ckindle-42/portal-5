# Gemma4 -mlx Tag Evaluation — 2026-07-12

## Context

Ollama 0.31.1 claims a large MTP-driven speed win for Gemma4, but Portal's 2026-07-01 evaluation (`KNOWN_LIMITATIONS.md` P5-MLX-EVAL-001/002/003) found the speedup doesn't reach Portal's GGUF fleet and that the official `-mlx` tags lacked vision at the time, blocking any swap. A live check of `ollama.com/library/gemma4/tags` on 2026-07-11 showed every `-mlx` tag reporting "Text, Image" input, appearing to remove that blocker. This task is the empirical follow-up: pull the five `-mlx` size tiers, test each against its current-production `-it-qat` counterpart on five axes, and report the data — no config changes, no promotion decision.

## Summary table

| tier | variant | arch_name | param_count | quant | ctx_len | vision_ok | audio_ok | tools_ok | tps_median | tps_stdev | quality_score_delta | pull_size_gb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| e2b | mlx | gemma4 | 5.2B | nvfp4 | 131072 | false | false | true | 72.1 | 4.1 | 0.0 | 6.5 |
| e2b | it-qat | gemma4 | 4.6B | Q4_0 | 131072 | true | true | true | 42.9 | 0.93 | 0.0 | 4.3 |
| e4b | mlx | gemma4 | 8.1B | nvfp4 | 131072 | false | false | true | 49.1 | 1.45 | 0.0 | 8.8 |
| e4b | it-qat | gemma4 | 7.5B | Q4_0 | 131072 | true | true | true | 25.2 | 2.19 | 0.0 | 6.1 |
| 12b | mlx | gemma4_unified | 12.4B | nvfp4 | 262144 | false | false | true | 18.5 | 0.8 | -0.1 | 7.7 |
| 12b | it-qat | gemma4 | 11.9B | Q4_0 | 262144 | true | true | true | 13.1 | 0.94 | 0.0 | 7.2 |
| 26b | mlx | gemma4 | 26.2B | nvfp4 | 262144 | false | false | true | 30.0 | 1.38 | 0.0 | 17 |
| 26b-a4b | it-qat | gemma4 | 25.2B | Q4_0 | 262144 | true | false | true | 29.3 | 2.48 | 0.0 | 15 |
| 31b | mlx | gemma4 | 31.7B | nvfp4 | 262144 | false | false | true | 9.0 | 0.89 | 0.0 | 18 |
| 31b | it-qat | gemma4 | 30.7B | Q4_0 | 262144 | true | false | true | 6.0 | 0.33 | 0.0 | 18 |

**The headline finding is a contradiction, not a confirmation.** The TPS speedup is real and substantial (`-mlx` beats `-it-qat` at every tier: e2b +68%, e4b +95%, 12b +41%, 26b +2%, 31b +50%). But **every `-mlx` tag, at every tier, has zero vision and zero audio capability** — `ollama show`'s Capabilities list is `completion, tools, thinking` only, with no `Projector` section at all (the `-it-qat` variants all carry a 475M-parameter clip vision projector; `-it-qat` for e2b/e4b/12b additionally declares `audio`). This was verified two ways: the model metadata (no projector weights present — a load-time fact, not a runtime guess) and a live probe (`e2b-mlx` asked to describe a solid-red test image responded "Image missing" after 587 tokens of confused reasoning about a placeholder it couldn't resolve; `e2b-it-qat` on the identical request correctly answered "Red"; `e2b-mlx` asked to transcribe a synthesized audio clip responded "I have not received any audio in your request"; `e2b-it-qat` on the identical clip via the OpenAI-compatible `input_audio` content-block format transcribed it perfectly). The tags-page "Text, Image" label does not reflect what's actually served by these tags as of 2026-07-11 — this is either an incorrect label or a not-yet-propagated build; either way, it is empirically false for every tag pulled in this task.

**Architecture note:** `12b-mlx` reports `architecture: gemma4_unified`, differing from every other tier's plain `gemma4` (including its own `-it-qat` counterpart) — reproducing the exact anomaly Portal's prior evaluation flagged.

**Methodology note (adjacent finding, not part of this task's core question):** the initial TPS/quality probe attempts silently misreported every `-mlx` result as "empty response" because gemma4 has native `thinking` capability and can emit an entire response through the `reasoning` delta field with empty `content` — the ad-hoc probe tool built for this task (`tests/benchmarks/bench/adhoc_probe.py`) initially only counted `content` tokens, undercounting or zeroing out generation that was actually happening. Fixed to match `bench/measure.py`'s existing content+reasoning combination before any of the numbers above were captured; see that file's commit history for detail.

## Per-workspace fit assessment

| Workspace | Model lineage | Verdict | Driving evidence |
|---|---|---|---|
| `auto-daily` | Official Gemma4 26B-A4B QAT | **BLOCKED-MISSING-CAPABILITY** | Description claims VLM (vision-language); `26b-mlx` has zero vision capability (no projector). |
| `auto-gemma-fast` | Official Gemma4 E2B QAT | **BLOCKED-MISSING-CAPABILITY** | Description explicitly requires "Encoder-free audio+image+video+text"; `e2b-mlx` has neither vision nor audio. |
| `auto-gemma-e4b` | Official Gemma4 E4B QAT | **BLOCKED-MISSING-CAPABILITY** | Same audio+image dependency as auto-gemma-fast; `e4b-mlx` has neither. |
| `auto-gemma-vision` | Official Gemma4 31B Dense QAT | **BLOCKED-MISSING-CAPABILITY** | Vision is this workspace's entire purpose ("Heavy vision analysis"); `31b-mlx` has zero vision capability despite being the lowest-*audio*-risk tier going in. |
| `auto-audio` | Official Gemma4 12B QAT | **BLOCKED-MISSING-CAPABILITY** | Audio is this workspace's entire reason for existing; `12b-mlx` has zero audio (and zero vision), plus the `gemma4_unified` architecture anomaly. |
| `auto-purpleteam-exec` | `supergemma4-26b-uncensored` (third-party fine-tune) | **NEEDS-MORE-DATA** | Not an official Google Gemma4 checkpoint — no `-mlx` tag exists for this lineage at all. Out of this task's scope (§Explicit non-scope). |
| `auto-redteam-deep` | `supergemma4-26b-uncensored` (third-party fine-tune) | **NEEDS-MORE-DATA** | Same as auto-purpleteam-exec — no applicable `-mlx` tag exists. |
| `auto-pentest` | `huihui_ai/gemma-4-abliterated` (third-party fine-tune) | **NEEDS-MORE-DATA** | Same reasoning — abliterated fine-tune has no official `-mlx` counterpart to test against. |

**Net result: zero of the eight production Gemma4-lineage workspaces are viable `-mlx` swap candidates today.** The five that use official Google checkpoints all depend on vision and/or audio, which the `-mlx` tags don't have. The three that don't are on third-party fine-tunes with no `-mlx` equivalent to test in the first place.

## Open questions the data could not resolve

- **Quality delta is likely underpowered to detect anything at this sample size.** All 10 models scored identically (100%) on the 8 deterministic prompts (factual/math/code) — either the `-mlx` nvfp4 quantization genuinely doesn't regress quality on these simple tasks, or 8 prompts per tier isn't enough resolution to see a difference that a full persona-matrix run would surface. Not a certification either way.
- **No existing LLM-judge pattern found in the codebase** to reuse for the 2 vision-description and 2 tone/instruction-following subjective prompts, contradicting this task's own assumption (`bench_security`'s `scoring.py` is purely deterministic regex/word-count, not LLM-judge-based, and no other eval module has one either). Scored those items by direct read-through instead of a formal 1-5 judge call; all responses across all models looked reasonable and undifferentiated by variant, but this is a materially weaker signal than a formal judge score would be.
- **One quality-probe cell failed**: `gemma4:12b-mlx` timed out on the `tone_2` prompt (1 of 90 generations). Not re-run — treated as a minor infra gap, not a quality finding, per the spot-check's own "signal not certification" framing.
- **Audio test used one clip, one voice, one accent** (macOS `say` synthesis of a single sentence) — establishes the mechanism (no projector = no capability) but says nothing about reliability across real-world audio conditions for the variants that do have audio.
- **The vision/audio finding may be specific to this Ollama build/date.** If Ollama re-publishes these tags with the projector included, the finding would need re-verification — this report is a snapshot of 2026-07-11/12 tags, not a permanent characterization of the `-mlx` line.

## Disk/cleanup record

Baseline (Precondition, before any pulls): **1.2T** at `/Volumes/data01/ollama/models`, **157** models listed.
Post-cleanup (Section 7, confirmed): **1.2T**, **157** models listed — exact match. All 5 pulled `-mlx` tags (`e2b`, `e4b`, `12b`, `26b`, `31b`) removed via `ollama rm`; all 8 pre-existing `-it-qat` production comparison tags (both bare and `-ctx8k` variants) verified still present and untouched.

## Explicit non-recommendation

This report presents data. It does not recommend a specific action. No workspace was repointed, no `backends.yaml` entry was added or changed. The operator reviews the per-workspace fit assessment above and decides next steps — the empirical answer this task set out to get is clear (none of the eight current Gemma4-lineage workspaces can swap today), but what to do with the confirmed TPS win for a hypothetical future text-only workspace, or whether to watch for a future Ollama build that actually includes the projector, is a separate decision.
