# oMLX vs Ollama — Follow-up Probes (tool-calling under load, grammar livelock, pipeline shadow-shift, vision/VLM)

**Supersedes:** nothing — additive to `OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V4_20260805T210500Z.md`, which is the primary verdict document. This closes all four gaps that report flagged as untested: tool-calling under load, grammar livelock reproduction, the actual pipeline path under sustained load, and VLM/vision correctness (§4, added after the initial version of this report shipped without it).

**Harness:** new `tests/benchmarks/bench_omlx_stress_extras.py` (`tools_load`, `grammar_livelock`, `vision` probes), reusing `bench_omlx_v3.py`'s `one_request`/model matrix. Not merged into the `GATES` ladder — one-off follow-ups, not part of Phase-0.

## 1. Tool-calling under sustained concurrency

**Method:** repeat the Gate-3 tool-call probe continuously for 90s at concurrency=5, classify every response (`tool_call` / `text_only` / `no_tool` / `error`).

| Model | Engine | Requests | tool_call rate | Verdict |
|---|---|---|---|---|
| Qwen3-Coder-30B-A3B (coder) | oMLX | 216 | 97.7% (211/216, 5 no_tool) | DEGRADED (marginal) |
| Qwen3-Coder-30B-A3B (coder) | Ollama | 352 | 100% (352/352) | PASS |
| gemma-4-e4b (gemma) | oMLX | 277 | 100% (277/277) | PASS |
| gemma4:e4b-it-qat (gemma) | Ollama | 60 | **53.3%** (32/60, 28 no_tool) | **DEGRADED** |

**Finding:** this is the one place the earlier report's "both engines are equally reliable" framing needed a correction. At single-shot (Gate 3 in the original Phase-0 run), both engines pass cleanly on Qwen/Gemma. Under sustained concurrent load, Ollama's gemma tool-calling **degrades sharply** — under half of concurrent requests actually emit a structured `tool_calls` payload, the rest silently fall back to plain prose (`no_tool`, not an error — this would pass a naive check and only shows up if you inspect the response body). oMLX's gemma held 100% under identical load. Ollama's coder path stayed at 100% throughout, and oMLX's coder path showed a small (2.3%) miss rate — worth noting but far smaller than the gemma-on-Ollama gap. Ollama's lower raw request count (60 vs oMLX's 277 for gemma) is itself a byproduct of the same tail-latency pattern documented in V4 — slower requests mean fewer complete in the fixed window.

## 2. Grammar livelock reproduction attempt

**Method:** alternate an unconstrained plain-text request with a constrained `json_schema` request, sequentially, on the flagged model (oMLX gemma-4-e4b), looking for the hang OMLX_DECISION.md describes as "one reproducible gemma livelock on unconstrained→constrained transitions."

- 20 cycles, then 40 more cycles (60 total): **0 livelocks**. Every unconstrained call ~0.8-0.97s, every constrained call ~0.70-0.76s, flat and consistent throughout.

**Finding:** not reproduced under simple sequential alternation. The original note describes it as reproducible-but-rare, so a clean 60/60 doesn't rule it out — it suggests the trigger needs either concurrent unconstrained/constrained requests racing (not tested here) or a specific schema/prompt shape not covered by the router-classification schema used in Gate 4. Treat as **open, lower urgency** rather than resolved — no regression risk found, but the reproduction case wasn't hit.

## 3. Pipeline shadow-shift under sustained load

**Method:** `bench_omlx_v3.py --gate shootout --url http://localhost:9099 --models auto-coding`, matched to the V4 direct-engine defaults (120s, concurrency=5), through the actual production endpoint — Bearer-authed, routed through `router_pipe.py`'s shadow-shift (`omlx-coding`, priority 10, Ollama fallback) rather than hitting `:8085`/`:11434` directly.

| metric | value |
|---|---|
| ok/total | 14/14 |
| failures | 0 |
| ttft p50/p95/p99 (s) | 0.657 / 2.344 / 2.481 |
| tps_mean | 20.9 |
| tps_cv | 0.204 |
| truncated | 3/14 |

**Finding:** zero failures, and critically the tail shape (p99=2.48s, not hundreds of seconds) matches oMLX's direct-engine profile from V4, not Ollama's blowup-under-load profile (which hit p99s of 66-333s at similar concurrency). This is the strongest confirmation yet that the shadow-shift routing is actually landing traffic on oMLX under real load through the production path — not silently falling back to Ollama and masking the difference.

## 4. VLM / vision correctness and capability

**Method:** `vision` probe added to `bench_omlx_stress_extras.py` — `one_request`'s `messages` param already accepts arbitrary content, so no changes to `bench_omlx_v3.py` were needed, just an image-payload builder (base64 PNG data URIs) and three synthetic, ground-truth-verifiable images (`tests/benchmarks/assets/`): a red circle (shape/color), 5 bars of increasing height (counting), and rendered text "PORTAL5" (OCR). Three quant-matched pairs, chosen from `config/backends.yaml`'s registered vision/`omlx` groups and verified with `du -shL`:

| Pair | oMLX model (size) | Ollama model (size) |
|---|---|---|
| qwen-vl | Qwen3-VL-32B-Instruct-4bit (18GB) | qwen3-vl:32b-ctx8k (20.9GB) |
| supergemma-vl | supergemma4-26b-abliterated-multimodal-mlx-4bit (15GB) | supergemma4-26b-uncensored:Q4_K_M-ctx64k (16.8GB) |
| gemma-e4b-vl | gemma-4-e4b-it-4bit (4.8GB) | gemma4:e4b-it-qat-ctx8k (6.1GB) |

First pass used `max_tokens=100` and produced two false FAILs on Ollama's gemma4-e4b (empty content, `finish_reason=length`) — live-checked and root-caused: this checkpoint's Ollama default is thinking-ON (documented previously in `OMLX_DECISION.md`: "oMLX serves this same checkpoint with `thinking_default=False`"), so it burned the whole budget on reasoning before reaching an answer. Re-ran at `max_tokens=500` for both engines; results below are the corrected run.

| Pair | Engine | shape_color | bar_count | ocr_text | Score |
|---|---|---|---|---|---|
| qwen-vl | oMLX | PASS | PASS | PASS | 3/3 |
| qwen-vl | Ollama | PASS | PASS | PASS | 3/3 |
| supergemma-vl | oMLX | PASS | PASS | PASS | 3/3 |
| supergemma-vl | Ollama | **FAIL** (HTTP 400) | **FAIL** (HTTP 400) | **FAIL** (HTTP 400) | 0/3 |
| gemma-e4b-vl | oMLX | PASS | PASS | PASS | 3/3 |
| gemma-e4b-vl | Ollama | PASS | **FAIL** (miscounted "6") | PASS | 2/3 |
| **Total** | **oMLX** | | | | **9/9** |
| **Total** | **Ollama** | | | | **5/9** |

**Findings, two different in kind:**

1. **supergemma4-26b is not a real apples-to-apples pair.** Ollama's `supergemma4-26b-uncensored:Q4_K_M` GGUF returns a hard `HTTP 400 "Multimodal data provided, but model does not support multimodal requests"` — this GGUF conversion is text-only, full stop, regardless of prompt or token budget. Consistent with `config/backends.yaml`'s own `vision` group (line ~430) never listing a `supergemma4` entry — only oMLX's `omlx-local` group claims a multimodal `supergemma4-26b-abliterated-multimodal` build. This isn't an oMLX-wins-on-load story; it's oMLX having a capability (vision) for this checkpoint family that no equivalent production Ollama tag currently has at all. Worth knowing if any workspace is assuming vision on this model via Ollama — it will hard-fail.
2. **gemma-e4b-vl and qwen-vl are genuine matched capability tests**, and oMLX passed all 6, Ollama passed 5/6 (one bar-counting miss, a plausible model-accuracy issue on 3 samples, not indicative on its own).

## Consolidated take

Three of four follow-ups reinforce or extend the V4 verdict: the pipeline path holds up exactly like the direct-engine data predicted, grammar livelock is a non-issue for the common transition pattern, and vision correctness is comparable on genuinely matched pairs (oMLX 6/6, Ollama 5/6) with the gap widening only where Ollama's model catalog lacks a true equivalent (supergemma4 multimodal). The tool-calling probe adds the most actionable new finding: Ollama's gemma tool-calling is not just slower under load, it silently produces fewer valid tool calls (53% vs oMLX's 100%) — a correctness regression under load, not just a latency one. Given `SUPERGEMMA4` and gemma-family models are used across security workspaces per `reports/OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V4`, this strengthens rather than weakens the case for oMLX as the concurrent-load choice, and the vision pass adds a capability dimension (not just performance) where oMLX has strict parity or an edge.

## Provenance

- Tool-calling: `results/omlx_v3_tools_load_followup1_{omlx,ollama}_*.json`
- Grammar livelock: `results/omlx_v3_grammar_livelock_followup1{,_x40}_omlx_*.json`
- Pipeline shootout: `results/omlx_v3_shootout_pipeline_shadowshift_followup_ollama_20260806T004753Z.json` (filename says `_ollama` — a harness naming quirk present *at run time*: engine-name detection keyed off `"8085" in url`, and `:9099` fell through to the `else` branch; fixed afterward in `bench_omlx_v3.py` so future `:9099` runs tag as `pipeline`. The run itself hit `:9099` with `auto-coding`, confirmed by the `url` field inside the JSON)
- Vision (corrected, max_tokens=500): `results/omlx_v3_vision_followup2v2_{omlx,ollama}_*.json`; superseded max_tokens=100 run kept for the record at `results/omlx_v3_vision_followup2_*.json`
- Vision test assets: `tests/benchmarks/assets/vision_probe_{shape,bars,text}.png`
- New harness: `tests/benchmarks/bench_omlx_stress_extras.py`
- HEAD at run time: `33055b4c` (tool-calling/livelock/pipeline sections); vision section added same session, harness fix included
