# Engine upgrade — Ollama 0.35.0, oMLX 0.7.0 (2026-10-01)

Both engines moved to the latest **stable** release (no RCs) and were tested
through the pipeline. Gate: `scripts/engine_contract_check.py` (both pass).

## Outcome

| Engine | From → to | Verdict |
|---|---|---|
| Ollama | 0.34.4 → 0.35.0 | adopted; seat A/B identical within noise |
| oMLX | 0.6.4 → 0.7.0 | adopted; seat A/B at least as good; needs `aggressive` tier for REAP-288 only |

## What the first oMLX attempt got wrong (and why it was rolled back)

The autoupdater's contract probe rejected 0.7.0 twice over. Both were probe
fragility, not engine bugs:

- `presence_penalty`: still honoured, but 0.7.0 corrected Qwen3.5/3.6 GDN numerics, so the
  probe prompt's greedy output shifted and a 2.0 penalty no longer flips it (it needs 10.0 there;
  0.6.4 flipped at 1.0). Probe now escalates 2.0 / 5.0 / 10.0.
- `think:true`: the model needs slightly more than the old 600-token cap to finish thinking.
  A response cut off mid-thought leaks thinking into `content` on **both** versions (the
  Qwen3.5 template prefills `<think>`, so no tag is left to split on). Probe cap is now 2000.

## Real finding: pipeline tool_call deltas had no `index`

oMLX 0.7.0 returns parallel tool calls for Qwen3-Coder. The pipeline re-streamed them
(`router/streaming.py`, buffered-completion and client-tools passthrough paths) with no `index`,
so OpenAI-style clients merged them (`file_writefile_writepytest_run`). Smoke: 0.6.4 PASS 2/2,
0.7.0 FAIL 4/4 before the fix, PASS 3/3 after. Affects clients that bring their own tools
(IDE lanes, the WFE harness), not Open WebUI.

## Seat A/B (pipeline, n=3, same seats/models, only the engine differs)

oMLX (42 rows per arm): Laguna-XS-2.1 22 → 27 PASS; Qwen3-Coder-30B 17 → 21 PASS
(`code-kv` fails on both versions).

Ollama (36 rows per version): gemma4-e4b 9/9 → 9/9; Nex-N2-mini 9/9 → 9/9;
KAT-coder 8/9 → 8/9; omnicoder2 9/9 → 8/9 (one budget-exhausted row, noise at n=3).

Plans: `tests/wfe/plans/engine_ab_omlx.yaml`, `engine_ab_ollama.yaml`.

## Memory guard (oMLX 0.7.0 rebuilt it)

`ceiling = min(static, dynamic, metal_cap)`; `dynamic = oMLX resident + free + inactive − tier reserve`.
Tier reserve on this 64GB Mac: safe 12.8 GiB, balanced 5.1, aggressive 1.5.
Measured with the stack up: balanced 40.5 GiB, aggressive 48.7 GiB (Metal cap 56.1).

REAP-288 (IDE only, stack down), measured:

| Tier | Result |
|---|---|
| balanced | rejected: prefill peak ~39.97 GB vs dynamic ceiling 39.81 GB, even for a one-word prompt |
| aggressive | loads; a 15.3K-token prefill served at 29.8 tok/s |

Decision: daily operation stays `balanced` (largest regular oMLX models are far below 40 GiB);
`./launch.sh coder-reap288` sets `aggressive` (`scripts/omlx_memory_tier.py`) and
`./launch.sh up` restores `balanced`. The 56GB `wired_limit` is unchanged.

## Lightning MTP on 0.7.0

Native (`omlx.patches.mlx_lm_mtp`, 93–98% draft acceptance); no MTPLX side-car process runs.

| Model | tok/s (0.7.0) | Reference |
|---|---|---|
| Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp | 90 | 70 on 0.6.x, 53 on Ollama |
| Qwen3.8-27B-oQ4e-mtp | 42 | 6.8–9.5 on Ollama |

## Seats exercised through the pipeline

12 seats answered correctly with no leaked thinking (security redteam/purpleteam/pentest/blueteam/base,
nemotron, reasoning::deep, documents, research, data, vision, general-uncensored). `auto-compliance`
is served by `Qwen3.8-27B-oQ4e-mtp` and passed its WFE smoke.

## Not tested

Open WebUI itself, and the long compliance_agentic suite on the new engines.
