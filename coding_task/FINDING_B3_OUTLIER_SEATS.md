# FINDING — four B3 seat outliers and two no-answer rows (post080_fix4, 2026-11-20)

Run: `~/.portal5/omlx080/post080_fix4` (B3 `speed_bench --engine pipeline`, 21 seats,
sizes 2000/8000/32000; Pipeline log `~/.portal5/omlx080/evidence/pipeline_post080_fix4.log`;
oMLX log `~/.omlx/logs/server.log` window 13:34–13:46 local; B1 direct rows
`~/.portal5/omlx080/post080_fix3/b1_*.json`). Every number below is read from those files;
this lane made no live request.

## Summary

Four seats were reported decoding at 24–72 % of the same model measured direct, and two
seats produced no answer. **None of the six is a slow model.** Three causes explain all six:

| cause | seats | real defect? |
| --- | --- | --- |
| The seat spends two model calls on one request (tool policy), and the timing rollup counts the discarded call's decode seconds against the delivering call's tokens | bigfix, cad 8k, data | **yes — Pipeline timing rollup** (`trace.py`) |
| The seat carries a fixed system+tool prompt of 1–8 k tokens, so its real prompt at nominal size 2k/8k is 2–7× the direct row's; decode falls with prompt length | cad, reading, data, bigfix (all rows) | no — inherent to the seat; the "% of direct at nominal size" metric is comparing different prompt lengths |
| `speed_bench` caps output at 128 tokens: a `tool_choice: required` call cannot finish in 128 tokens (it is retried), and a `think: true` model spends the whole budget on reasoning and is reported NO ANSWER | bigfix, cad 8k, pentest, reasoning::deep | **yes — bench measurement** (`speed_bench.py`) + a reporting classification; the no-answer itself is the 128-token cap, not the seat |

After the two code fixes and comparing at the seat's **actual** prompt length, all six are
≥ 90 % of the same model measured direct — except `auto-compliance::reading` at 2k (84 %,
first request after a cold load).

## Per-seat cause table

`reported` is `decode_tps` in the B3 JSON as written (the number in the brief). `engine` is the
oMLX log's own rate for the delivering hop (`Chat completion: …, N tokens in Ts (R tok/s)`).
`calls` counts model calls the Pipeline made for that one bench request, from the oMLX log.
`direct@prompt` is the B1 row for the same model linearly interpolated to the seat's actual
`prompt_tokens` (B1 points are 1.5 k / 5.8 k / 23 k prompt tokens).

| seat | size | calls | reported | engine | seat prompt | direct@prompt | engine/direct | cause |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| auto-coding::bigfix | 2k | 2 | 40.8 | 75.6 | 2444 | 78.8 | **96 %** | 2 calls + rollup |
| auto-coding::bigfix | 8k | 2 | 17.0 | 66.3 | 6808 | 68.2 | **97 %** | 2 calls + rollup |
| auto-coding::cad | 2k | 1 | 57.9 | 57.8 | 9642 | 63.8 | **91 %** | 8.2 k fixed prompt |
| auto-coding::cad | 8k | 2 | 26.3 | 52.6 | 14028 | 57.0 | **92 %** | 2 calls + rollup + 8.2 k fixed prompt |
| auto-research::data | 2k | 2 | 21.0 | 69.7 | 3115 | 72.3 | **96 %** | 2 calls + rollup |
| auto-research::data | 8k | 2 | 47.4 | 69.5 | 7479 | 71.1 | **98 %** | 2 calls + rollup |
| auto-compliance::reading | 2k | 1 | 46.0 | 45.8 | 5637 | 54.6 | **84 %** | 4.2 k fixed prompt + cold first request |
| auto-compliance::reading | 8k | 1 | 45.1 | 44.9 | 10001 | 48.8 | **92 %** | 4.2 k fixed prompt |
| auto-security::pentest | 2k | 1 | 92.8 | 92.4 | 3310 | 92.2 | **100 %** | no answer (128-token cap) — decode was always fine |
| auto-security::pentest | 8k | 1 | 88.3 | 88.2 | 7674 | 89.0 | **99 %** | no answer (128-token cap) — decode was always fine |
| auto-reasoning::deep | 2k | 1 | 27.1 | 27.1 | 1507 | 23.2 | **117 %** | no answer (128-token cap); the MTP seat is faster than its B1 row |

Same-model control: **auto-daily::fast runs the identical oMLX weights**
(`unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit`) and measures 64.5 / 69.0 tok/s (89 / 96 % of direct).
`auto-research::data` is the same checkpoint on the same backend group; the two differ only in
seat config: `data` has `require_tool_before_answer: true`, 7 tools and a 1.7 k fixed prompt,
`fast` has 79 tools and `require_tool_before_answer` unset. `data`'s engine rate is 69.7 / 69.5
— identical to `fast`. The model is not the difference.

## Cause 1 — two calls per request, and the rollup charges the discarded call's time

`auto-coding::bigfix` and `auto-coding::cad` are `tool_choice: required`;
`auto-research::data` is `require_tool_before_answer: true`. The bench prompt is filler text,
so hop 1 answers without a tool call and the Pipeline correctly withholds it and asks once more
(`Tool loop hop 1: … answered without a tool call; asking once for a tool call first` /
`… for a grounded answer`). Two engine calls, one delivered answer:

| seat/size | hop 1 (discarded) | hop 2 (delivered) | row `total_s` |
| --- | --- | --- | --- |
| bigfix 2k | 77 tok, ttft 2.63, gen 0.98 s | 128 tok, ttft 0.46, gen 1.69 s | 5.77 = 3.62 + 2.15 |
| bigfix 8k | 116 tok, ttft 6.42, gen 1.70 s | 39 tok, ttft 0.70, gen 0.57 s | 9.42 = 8.13 + 1.29 |
| data 2k | 107 tok, ttft 2.93, gen 1.51 s | 46 tok, ttft 3.01, gen 0.65 s | 8.10 = 4.44 + 3.66 |
| data 8k | 56 tok, ttft 5.90, gen 0.79 s | 119 tok, ttft 5.88, gen 1.70 s | 12.06 = 6.69 + 5.37 |
| cad 8k | 128 tok, ttft 0.63, gen 2.44 s (truncated `<tool_call>` envelope) | 128 tok, ttft 0.89, gen 2.43 s | 6.62 = 3.33 + 3.29 |

The row's `answer_tps` is **the delivered hop's tokens divided by both hops' decode seconds**:
`16.957 = 39 / (1.70 + 0.57)` for bigfix 8k, `21.005 = 46 / (1.51 + 0.65)` for data 2k. So the
reported percentage is `engine_rate × delivered_tokens / all_hops_tokens` — exactly the ratio
that makes a 70–76 tok/s seat look like 17–41 tok/s.

The defect is in `portal/platform/inference/router/trace.py`. `_record_tool_loop_turn` marks a
discarded hop with `tool_turn=True, answer_tokens=0, answer_s=0`; `_answer_token_count` honours
that (answer tokens 0), but `_resolve_durations` ignores the explicit `answer_s=0` and recomputes
it with `_answer_duration(…)` from the engine `generation_duration` (because `has_answer` is true
from the hop's `answer_deltas`). Result: a discarded hop contributes **0 tokens and its full
decode time** to the request rollup. Reproduced offline with the repo's own `_tool_loop_frames`
(`coding_task/scratch/probe_timings_hops.py`): hop 1 normalizes to
`answer_tokens=0, answer_s=0.98`, rollup `128 / 2.67 = 47.94` instead of the delivered hop's
`128 / 1.69 = 75.74`.

This is not only a bench artifact: every agentic seat that calls a tool before answering has its
`answer_tps` understated by the tool hop's generation time (the same rollup feeds
`metrics_state.json` and the usage records).

**Fix:** `_resolve_durations` sets `answer_s = 0` for a `tool_turn`, matching the token side.
Regression test drives a two-hop require-tool retry and asserts the rollup's `answer_tps` is the
delivered hop's engine rate.

## Cause 2 — a fixed system+tool prompt inflates the real prompt at nominal size

The bench sizes filler text only: `build_filler_prompt(n)` produces `n*4` characters, which
tokenize to **0.727 tokens per nominal token** (0.727 is derived from two seats' own rows and
holds for every seat checked: `heavy` 4039−1454.5 = 2585 and 8403−5818 = 2585). The per-seat
overhead is therefore constant and measurable as `prompt_tokens − 0.727 × size`:

| seat | tools | system prompt | fixed prompt tokens | real prompt at 2k / 8k |
| --- | ---: | --- | ---: | --- |
| auto-coding::bigfix | 3 | none | ~990 | 2.4 k / 6.8 k |
| auto-coding::cad | 20 | 3772-char append | **~8 190** | 9.6 k / 14.0 k |
| auto-research::data | 7 | 164-char owui prompt | ~1 660 | 3.1 k / 7.5 k |
| auto-compliance::reading | 19 | 6663-char append + 624-char owui | ~4 180 | 5.6 k / 10.0 k |
| auto-daily::fast (control) | 79 | 426-char append | ~5 045 | 6.5 k / 10.9 k |
| auto-security::pentest | 7 | 1651-char append | ~1 855 | 3.3 k / 7.7 k |
| auto-reasoning::deep | 0 | 153-char owui prompt | ~53 | 1.5 k / 5.9 k |

Decode tok/s falls steeply with prompt length on this hardware: the same
Qwen3-Coder-30B-A3B checkpoint measures 81.4 / 69.8 / 42.6 tok/s at 1.5 k / 5.8 k / 23 k prompt.
So a 2k bench row for `cad` is not a 2k-prompt measurement — it is a 9.6 k-prompt measurement
compared against a 1.5 k-prompt baseline. `cad`'s 71 % at 2k becomes 91 % once the comparison
uses the seat's own prompt length. `reading`'s 83 % at 8k becomes 92 %.

The tool counts and prompt-append lengths are the seats' job (`cad` is the parametric-CAD
workspace; `reading` is document compliance reading) — this is the "inherent to the seat" case in
the brief, and the number to quote is the fixed prompt above, not a code defect.

## Cause 3 — the 128-token output cap: truncated required tool calls and all-reasoning answers

`speed_bench.NUM_PREDICT = 128` is sent as `max_tokens` (Pipeline) on every request, and the
Pipeline's `body.setdefault("max_tokens", predict_limit)` cannot override a caller value. Two
different failures follow:

* **Required tool call truncated** (`cad` 8k): hop 1 stops with an *unclosed* tool-call envelope
  (`Unclosed tool-call envelope at end of stream; withheld 69 characters … '<tool_call>\n<function=generate_part>…'`).
  It cannot be parsed, so the Pipeline treats the hop as "answered without a tool call" and
  retries — the second call of Cause 1.
* **All-reasoning answer** (`pentest` 2k/8k, `deep` 2k): the seat is `think: true`; the engine
  reports `finish_reason=length`, `completion_tokens=128`, `reasoning_tokens=129`. The Pipeline
  logs `completed without answer content … reasoning_only=True` and emits
  `⚠️ The model did not produce an answer`. One call per request; no retry. `deep` at 8k needs
  103 of 121 generated tokens for reasoning and then answers, which is why 8k is fine.

Both are the bench cap, not the seat. The 128 reasoning tokens are a perfectly valid decode
sample (pentest 92.4 / 88.2 tok/s = 99–100 % of direct), so the bench now reports a
budget-exhausted reasoning reply as `seat_status: reasoning_only` (with the reasoning and
completion counts kept) instead of `no_answer`, and `speed_gate` treats it as a note and keeps it
in the comparison. A seat that must *answer* still needs a larger cap; that is a bench-parameter
decision, recorded in OPEN.

## Measurement caveats that remain

* **Short generations.** `reading` answers the filler prompt in 23 tokens (8k: 23, 32k: 32)
  while B1 generates 128. oMLX's rate over 23 tokens carries a ~70 ms fixed per-request decode
  cost: at prompt 5637 the same model's fitted per-token cost is 18.7 ms, and the 2k row implies
  21.8 ms (`1000/45.8`), i.e. +68 ms over 22 steps. At 8k (22.4 ms observed vs 21.9 ms fitted,
  +8 ms) and 32k (+19 ms over 31 steps) the effect is noise. This explains `reading`'s residual
  84 % at 2k/8k; `reading` 32k is 89.6 % with an 18 % *longer* prompt than B1's row, i.e. at
  equal prompt it is at parity. The bench already records `completion_tokens`, so a short sample
  is visible.
* **No concurrency.** Each cell's `setup.before/after` shows only the target model resident; the
  oMLX log shows one `Chat completion` at a time per model. MCP tool discovery (185 tools / 28
  servers) runs before the first route in a cell.
* **Sampling / thinking / oMLX settings are not the difference.** `~/.omlx/model_settings.json`
  is per model, not per variant; the two Qwen3-Coder seats send the same sampling the server
  already defaults to (0.7 / 0.8 / 20 / 1.05) plus `min_p 0.05`. No speculative backend is
  selected for Coder or gemma (only `Qwen3.8-27B-oQ4e-mtp` has `mtp_enabled: true`). The
  Pipeline sends `chat_template_kwargs.enable_thinking` from the seat's `think`; `data`/`fast`
  (think false) show `reasoning_tokens: 0`, `pentest`/`deep` (think true) reason.

## Re-run command and pass criteria

```bash
uv run python scripts/speed_gate.py run post080_fix5 --out-dir ~/.portal5/omlx080 --phases B3
```

What must be true in `~/.portal5/omlx080/post080_fix5/`:

* Every cell `status` is `ok`; `run.json` counts `failed: 0`, `invalid_engine: 0`.
* `pentest` and `auto-reasoning::deep` rows are `seat_status: reasoning_only` (not `no_answer`)
  with `completion_tokens: 128` and `reasoning_tokens >= 128`; no `NO ANSWER` failure strings.
* `bigfix`, `data` and `cad` 8k `decode_tps` are the **delivered hop's** rate (75.6 / 69.7 /
  52.6), not 40.8 / 21.0 / 26.3 — this is the check that the `trace.py` fix reached the Pipeline.
  Recompute: `decode_tps × answer_s` in the row must equal the row's `completion_tokens`
  (with the old rollup, `answer_s` covers two hops and the product is ~2× too large).
* "% of direct" must be computed at the seat's own `prompt_tokens`, by interpolating the B1 rows
  for the same model (this document's table is the template). The nominal-size ratio will remain
  below 85 % for `cad` (8.2 k fixed prompt) and `reading` 2k/8k (4.2 k fixed prompt + 23-token
  sample): that is arithmetic, not a seat regression.
