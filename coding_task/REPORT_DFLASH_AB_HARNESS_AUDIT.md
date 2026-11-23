# DFlash A/B harness audit — root causes & fix (run 20261123T023745Z)

Lane: `lane/dflash-ab-harness-audit` · Brief: `coding_task/BRIEF_DFLASH_AB_HARNESS_AUDIT.md`
Forensic source: `/Users/chris/.portal5/dflash_ab/20261123T023745Z/` (read-only),
`docker logs portal5-pipeline`, `~/.omlx/logs/server.log`, oMLX 0.8.1 source at
`/Users/chris/omlx-live/venv/.../omlx/`.

## Root cause 1 — tool probe: the Pipeline cap-seal swallowed client-only calls

The model **did** emit a valid `fetch_weather` call in BOTH arms. Pipeline log
(2026-11-22 20:48 OFF / 20:50 ON):

```
NON-STREAM POST → ... model=Qwen3.8-27B-4bit 1 msgs, 2 tools
NON-STREAM tools: ['fetch_weather', 'list_saved_reports']
NON-STREAM ← ... | 1 tool_calls, content=''
POST http://host.docker.internal:8085/v1/chat/completions "HTTP/1.1 200 OK"   ← second turn
```

The probe's recorded prose ("I cannot synthesize a final answer or name sources
because no tool results were provided in the conversation history above") is a
direct reply to `CITED_SYNTHESIS_REQUEST` (`router/tool_repeat.py`). Path:
`auto-coding` declares `max_tool_calls: 10`, inherited by the
`qwen38coder-dflash` variant (`merge_workspace_variant`) →
`_ns_call_limit=10` → `seal_client_calls=True` →
`_seal_capped_client_calls` → `_replace_with_cited_answer` strips the
client-owned call and forces a toolless synthesis turn. The
`portal_client_tools_only` flag (popped at `non_streaming.py` L1279) was never
consulted by the seal. `Qwen3.8-27B-4bit` declares `supports_tools: true`
(verified live per `config/backends.yaml` comment) — **no config defect; no
config changed.**

Fix: `non_streaming.py` captures the flag and exempts client-only requests
from the seal (`seal_client_calls=_ns_call_limit is not None and not
_ns_client_tools_only`). The cap's purpose ("that restarts Open WebUI's tool
loop") does not apply to a client that explicitly brings its own toolset and
runs its own loop; the Pipeline dispatches nothing for such a request.

Harness defense: an OFF baseline probe failure now grades `INVALID_BASELINE`
(never `CORRECTNESS_REGRESSION`); ON-only failures still grade
`CORRECTNESS_REGRESSION`. Replaying the recorded run.json through the new
`compare_arms`: OLD `CORRECTNESS_REGRESSION` → NEW `INVALID_BASELINE`.

**Twin defect (reported, NOT fixed — out of brief scope):** the streaming path
has the same contract violation: `_client_tools_only` stays inside
`_build_streaming_request` (`streaming.py` L2912) and never reaches the tool
loop; `next_tool_action` (`tool_repeat.py` L292-307, "Capped workspaces never
hand calls back") synthesizes client-owned calls when `call_limit` is set
(`streaming.py` L1264, L1806). Any streaming client-only caller on a capped
workspace (e.g. `auto-coding::laguna` IDE traffic) is affected at code level;
production impact unverified — orchestrator decision.

## Root cause 2 — decode variance: sampled early-EOS, 2→128 completion tokens

`speed_bench.request_omlx` sent **no** sampling params, so oMLX applied the
per-model settings in `~/.omlx/model_settings.json` for `Qwen3.8-27B-4bit`:
`temperature 0.7, top_p 0.8, top_k 20, presence_penalty 1.5`. On the degenerate
`bench fill …` prompt, sampled continuations hit EOS at wildly different
lengths. Completion tokens inferred from `(total_s − ttft_s) × decode_tps`:

```
off rep1 32000: 0.10s window → ~1 token     on rep1 8000: 0.01s window → ~1 token (92.79 tok/s)
off rep2 32000: 0.08s window → ~1 token     on rep2 8000: 3.75s window → ~94 tokens (25.07)
off rep3 32000: 9.39s window → ~128 tokens  on rep3 8000: 3.52s window → ~128 tokens (36.37)
```

The engine's own log confirms it: `MTP[2] finish=stop tokens=2 cycles=0` — the
92.79 tok/s "decode" row was **two init tokens and zero speculative decode
cycles**; `MTP[8] finish=length tokens=128 accept=104/105 (99.0%)`. Acceptance
ranged 0%–99% with content. A 1–2-token window measures first-token overhead,
not decode; that is the entire 67.7 tok/s spread.

Fix: oMLX 0.8.1 supports `temperature`, `seed`, `ignore_eos`
(`api/openai_models.py` `ChatCompletionRequest`). The A/B now sends
`temperature=0, seed=42, ignore_eos=True` with the fixed `max_tokens=128`, so
every rep decodes exactly 128 tokens of a deterministic continuation —
like-for-like decode windows and stable acceptance. `speed_bench` gained
opt-in `temperature/seed/ignore_eos/cache_bust` params (defaults preserve
existing behavior for all other callers); oMLX rows now record
`completion_tokens` and `cached_tokens`.

## Root cause 3 — prefix-cache state differed across reps and arms

OFF rep1 prefill 113–127 tok/s (cold) vs rep2/3 17k–45k tok/s (warm); ON rep1
inherited OFF's cache (4075 tok/s at 2k); the filler prompts share prefixes
across sizes within a rep (4075 → 12676 → 27395). Fix: a unique leading nonce
per run/arm/rep/size (`[bench-nonce <stamp>-<arm>_rep<N>-<size>]`) busts the
prefix cache for every measured request; `cached_tokens` is recorded per row
so the receipt proves the cache state. Trade-off: every 32k request now pays
cold prefill (~180 s on this host), so a full run is longer (~35–40 min vs 13).

## Quality parity

`probe_seat` now runs four fixed prompts at greedy sampling: coding (126),
tool call (`fetch_weather`, client-only), reasoning (17*23+19=410),
instruction-following (`READY 11`, verbatim format check). Parity grading:
OFF-pass/ON-fail → regression; OFF-fail → `INVALID_BASELINE`. The receipt
gains per-rep sample tables (completion tokens, decode tok/s, cached tokens)
and the engine's per-sequence draft/verify counters (OFF arm must be empty).

## Files

- `portal/platform/inference/router/non_streaming.py` — seal exemption (2 lines + comment)
- `scripts/speed_bench.py` — opt-in sampling/cache controls, completion/cached token recording
- `scripts/dflash_ab.py` — deterministic arms, INVALID_BASELINE, 4-probe parity, stats capture, receipt
- `tests/unit/test_dflash_ab_harness.py` — 29 focused tests (grading, plumbing, seal, parsing)
- `tests/unit/test_dflash_ab.py` — fake answers the two new probes; fixtures carry the new fields

## Live verification owed (orchestrator)

Pipeline image must be rebuilt for the seal fix (`./launch.sh rebuild && ./launch.sh up`),
then re-run the A/B; see the dispatch report's ORCHESTRATOR RUNS block.
