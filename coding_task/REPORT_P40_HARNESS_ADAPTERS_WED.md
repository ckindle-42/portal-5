# REPORT — P40 harness-adapter seats (for the operator's Wednesday report)

Lane `lane/omlx081-intake`, 2026-11-21. Everything marked **measured** was executed on
thebrain (Tesla P40, 24 GB, driver 580.178.04) or on this Mac against thebrain over HTTP.
The Mac's Portal stack, its Ollama and its oMLX were not touched.

**Answer up front: keep the incumbent.** `qwen3.6-35b-a3b:q3code` under pi went 3/3 on the
three real tasks at 29–35 tok/s; the best candidate went 3/3 at 7.6–8.7 tok/s. Nothing here
shows an improvement big enough to re-seat the brain on a three-task sample, and one whole
harness path (opencode) did not complete a single task.

## 1. Baseline, measured on thebrain

| Fact | Value |
| --- | --- |
| GPU | Tesla P40, 24 576 MiB, driver 580.178.04 |
| Ollama | 0.40.16 (`OLLAMA_NUM_PARALLEL=4`, `KEEP_ALIVE=-1`, `FLASH_ATTENTION=1`) |
| llama.cpp | `0.9.0-dev` build 12138 `f7b41cca4`, CUDA, `~/llama.cpp/build/bin/llama-server` |
| Incumbent `qwen3.6-35b-a3b:q3code` | 17 GB, `num_ctx 131072`, loads at 18 891 MiB, 100 % GPU |
| Disk | `/` 693 G used / 1.1 T free after this lane |

## 2. Finding 1 — Ollama 0.40.16 cannot build a LoRA tag at all

The brief's first two candidates are Modelfiles with `ADAPTER`, i.e. `ollama create`. On this
box that is not a build that fails on memory or on adapter format — it is refused outright:

```
$ sudo -u ollama ollama create qwen38-27b-pi-lora:ctx32k -f /usr/share/ollama/adapters/qwen38-27b-pi-lora.modelfile
Error: LoRA adapters are no longer supported
```

The binary carries both `LoRA adapters are deprecated and will be removed in a future release`
and `LoRA adapters are deprecated; the adapter layer is carried over but new adapters cannot
be created`: an existing adapter tag keeps working, a new one cannot be made. `ollama create
--help` in 0.40.16 offers `--combine`, `--draft-quantize`, `--quantize` and no adapter flag.

**Consequence: none of the four candidates can be an Ollama tag on this box.** They are served
instead by the lane's own llama.cpp build, which supports `--lora` and is the path both
harness-hub cards prescribe. The served `--alias` is the brief's tag name, so the id the
harness sees is exactly the id the brief names:

```
llama-server -m <base.gguf> --lora <adapter-F16.gguf> -ngl 99 -c 32768 -fa on -np 1 \
  --host 0.0.0.0 --port 8091 --alias <tag> \
  --temp 0.8 --top-p 1.0 --top-k 0 --min-p 0 [-rea off]
```

`--temp/--top-p/--top-k/--min-p` bake the card's sampling exactly as `PARAMETER` does in a
Modelfile. `-rea off` is the card's "thinking off" for the Qwen3.8 adapters only (the Qwen3.8
template defaults to *medium*). It is deliberately **not** passed to LFM2.5 (its card says
"Always thinks before it answers") or to TwIL (its card publishes no thinking state).

Downgrading Ollama was considered and rejected: 0.40.16 is what the rest of the lane runs, the
incumbent tag is resident in it, and the brief says leave thebrain's default seat and the
dispatcher alone.

## 3. Setup proof per candidate (measured)

### 3.0 Intake check — is there anything newer in the family?

Read from the `harness-hub` org listing on 2026-11-21 (34 repos, creation dates via the HF API):

- The Qwen3.8 adapter family is the newest thing there: `pi-adapted`/`opencode-adapted`/
  `hermes-adapted` created 2026-11-16, `super-adapter` 2026-11-16. The GGUF repos were last
  modified 2026-11-18/20, but their file list and every file size still match the intake
  finding's record (318 802 304 / 318 802 400 B adapters, 28 595 763 840 B Q8_0),
  so no new weights landed. **No v2 of either specialist exists.**
- `Qwen3.8-27B-super-adapter` (one LoRA merging pi + Hermes + opencode) is the only newer Qwen3.8
  harness adapter, and its own card says it should be run with **thinking on** and is worse than
  each specialist on that specialist's harness with thinking off. Not a substitute here.
- `LFM2.5-24B-A2B-pi-v2` (2026-11-09) is the newest pi variant for that base — `-pi` v1 was
  2026-10-30, `-pi-v2` 2026-11-09, no v3. `LFM3-1.7B-pi` exists but is 1.7 B, not a brain seat.
- `TwIL-8B-pi` (2026-11-09) has no v2.

So the brief's named candidates are the current ones.

Common: base GGUFs are read straight from Ollama's blob store, so no second copy of any weights
exists on disk. Adapters live in `/usr/share/ollama/adapters/` (833 MB, world-readable;
`/home/jarvis` is mode 750 and not reachable by the `ollama` user).

### 3.1 `qwen38-27b-pi-lora:ctx32k`

| Item | Evidence |
| --- | --- |
| Base | Ollama blob `sha256-f5f1dd89…` = `qwen3.8:code32k`: `ollama show` → architecture `qwen35`, 27.3 B, **`Q4_K_M`**, ctx 262 144, GGUF `general.name = "Qwen3.8 27B 0814"` |
| Adapter | `Qwen3.8-27B-pi-lora-F16.gguf`, 318 802 304 B |
| Adapter is applied | `/lora-adapters` → `scale 1.0`; scale 0 vs 1 changes the first-token logprobs: `-0.05019 → -0.05880`, and the runner-up `print` `-3.8423 → -3.7220` |
| VRAM at load, ctx 32 768 | **18 741 MiB / 24 576** |
| Sampling served | `/props` → `temperature 0.8, top_p 1.0, top_k 0, min_p 0.0`, `n_ctx 32768` |
| Chat template renders | "Reply with OK" → `content "OK"`, `finish_reason stop` |
| Thinking state | `reasoning_content: null` (card: thinking off) |
| Tool call parses | `finish_reason "tool_calls"`, one `get_weather` with `{"location":"Little Rock, AR"}` |
| Unused tensors | `blk.64.*` (MTP/nextn head) ignored — llama.cpp does not use the draft head |

The Q8_0 base the card prefers is `Qwen3.8-27B-pi-Q8_0.gguf` at 28 595 763 840 B: **does not
fit 24 GB**, recorded as the brief asked.

### 3.2 `qwen38-27b-opencode-lora:ctx32k`

Same base and same numbers: adapter `Qwen3.8-27B-opencode-lora-F16.gguf` (318 802 400 B),
`/lora-adapters` `scale 1.0`, **18 741 MiB** at ctx 32 768, `/props` sampling 0.8/1.0/0/0,
`content "OK"` with `reasoning_content: null`, tool call parsed as `get_weather`.

### 3.3 `lfm2.5-24b-a2b-pi-v2:ctx32k`

| Item | Evidence |
| --- | --- |
| Base | `lfm2.5:24b-a2b-q4_K_M`, architecture `lfm2moe`, 24.0 B, **Q4_K_M**, 14 526 258 464 B. The card's Q8_0 (25 493 732 640 B) does not fit 24 GB |
| Adapter | `LFM2.5-24B-A2B-harbor-pi-lora-F16.gguf`, 37 438 208 B |
| Adapter is applied | scale 0 vs 1: first-token logprob `-0.5010 → -0.3189` |
| VRAM at load, ctx 32 768 | **15 529 MiB / 24 576** |
| Sampling served | `/props` → 0.8 / 1.0 / 0 / 0 |
| Chat template renders | 151 completion tokens to say "OK" — it always thinks first |
| Thinking state | **on, by design**: the base card says "Always thinks before it answers", and the template has no off switch |
| Tool call parses | `finish_reason "tool_calls"`, `get_weather` with the right argument |

Card notes worth carrying: this adapter was trained on **data-analysis** tasks (SmolDataEnvs),
`+2.7 ± 4.6` points over its base on that family and **`-5.0 ± 13.9`** on the harder
repository-task set; the card says outright it "does not improve on the base model" there.
Q5_K_M (17 029 602 592 B) and Q6_K (19 689 405 728 B) were **not** tried.

### 3.4 `twil-8b-pi:ctx32k`

| Item | Evidence |
| --- | --- |
| Base | `hf.co/mradermacher/TwIL-8B-GGUF:Q8_0`, architecture **`granite`**, 8.79 B, 9 345 614 528 B (card's own choice — it fits) |
| Chat template | `harness-hub/TwIL-8B-pi/chat_template.jinja`, 9 248 B, passed with `--chat-template-file` as the card's vLLM line does |
| Adapter | `TwIL-8B-harbor-pi-lora-F16.gguf`, 197 958 112 B |
| Adapter is applied | scale 0 vs 1: first-token logprob `-0.04007 → -0.03033` |
| VRAM at load, ctx 32 768 | **14 841 MiB / 24 576** |
| Sampling served | `/props` → 0.8 / 1.0 / 0 / 0 |
| Chat template renders | `content "OK"` plus a `reasoning` block |
| Thinking state | on — the card publishes none and its template defaults `enable_thinking = True` |
| Tool call parses | `finish_reason "tool_calls"`, `get_weather` with the right argument |

Non-commercial licence (webAI non-commercial v1.0), and the adapter was trained on the same
data-analysis family as 3.3 (`+3.4 ± 5.8` there).

### 3.5 Incumbent `qwen3.6-35b-a3b:q3code` (for symmetry)

`tool_calls` parsed with `{"location":"Little Rock, AR"}`; thinking on via its template;
tag sampling `temperature 0.6, top_k 20, top_p 0.95`, `num_ctx 131072`; loads at
18 891 MiB, 100 % GPU (it read 23 651 MiB resident mid-conversation at 128k).

### 3.6 Why prefill decides this lane

From the llama-server timings on the 27B base:

```
prompt eval time = 5345.70 ms / 797 tokens (149.09 tokens per second)
       eval time = 101634.70 ms / 1170 tokens (11.50 tokens per second)
```

**~11.5 tok/s decode, ~150 tok/s prefill** for a dense 27B at 32k on this card. The incumbent's
3B-active MoE runs at **29–35 tok/s** with the same harness. That ratio, not adapter quality,
is what the runs below mainly measure.

## 4. Task set (real, from this repo's git history)

Three small fixes that already landed here, replayed on their parent commit with only the fix's
own test applied. Each kit starts as a clean `git init` + one commit; grading is the real pytest
file, run after the harness stops, and nothing but the source fix passes it.

| Task | Base commit | Test | Before → after the real fix |
| --- | --- | --- | --- |
| t1 | `be354dacd^` | `tests/unit/test_jarvis_live_fails_r2.py` | 1 failed → 24 passed |
| t2 | `04ecd3e38^` | `tests/unit/test_timing_instrument.py` | 1 failed → 10 passed |
| t3 | `033fe18cf^` | `tests/unit/test_admin_reclaim_idle.py` (from `542c3109d`) | 4 failed → 12 passed |

Harness baseline, identical for every model and task: `pi 1.5.2 --thinking off --print
--no-session --mode json --no-skills --no-mcp --no-prompt-templates -nc`, provider
`openai-completions`, 1800 s wall cap for the opencode harness and 900 s for pi, cwd = the task
kit, prompt = the bug statement only ("…fix it so the failing tests pass. Do not modify any
test file."). opencode ran `2.3.2 --standalone --archived --auto --format json` with its own
config (`@ai-sdk/openai-compatible`) pointed at :8091.

## 5. Results

### 5.1 Pass / fail (pass = the fix's own pytest file green after the run)

| Seat | Harness | t1 | t2 | t3 | Score |
| --- | --- | --- | --- | --- | --- |
| **`qwen3.6-35b-a3b:q3code`** (incumbent, Ollama) | pi | pass 119 s / 14 turns | pass 266 s / 23 | pass 71 s / 10 | **3/3** |
| `qwen38-27b-pi-lora:ctx32k` (llama-server) | pi | pass 151 s / 8 | pass 197 s / 5 | pass 156 s / 7 | **3/3** |
| `qwen38-27b-opencode-lora:ctx32k` (llama-server) | opencode | fail 1800 s / 16 steps | fail 1800 s / 15 | fail 1455 s / 10 | **0/3** |
| `lfm2.5-24b-a2b-pi-v2:ctx32k` (llama-server) | pi | fail 900 s / 1 turn | fail 217 s / 18 | pass 900 s\* / 11 | **1/3** |
| `twil-8b-pi:ctx32k` (llama-server) | pi | pass 628 s / 13 | fail 900 s / 12 | pass 765 s / 11 | **2/3** |

\* LFM's t3 fix landed and graded 12 passed, but the agent was still working when pi hit the
900 s cap — counted as a pass on the real test, flagged because the harness did not converge.

### 5.2 Wall time and tokens

| Seat | t1 | t2 | t3 | out tok/s |
| --- | --- | --- | --- | --- |
| incumbent | 119 s, 3 160 out | 266 s, 5 824 out | 71 s, 1 978 out | 28.8 / 35.3 / 29.3 |
| qwen38-pi-lora | 151 s, 1 167 out | 197 s, 1 471 out | 156 s, 1 341 out | 7.9 / 7.6 / 8.7 |
| qwen38-opencode-lora | 1800 s, 1 660 out | 1800 s, 1 035 out | 1455 s, 1 396 out | 0.9 / 0.6 / 1.0 (wall) |
| lfm2.5-pi-v2 | 900 s, 142 out | 217 s, 11 872 out | 900 s, 11 391 out | 49 / 60.6 / 56.7 |
| twil-8b-pi | 628 s, 8 500 out | 900 s, 14 333 out | 765 s, 11 235 out | 15.0 / 17.8 / 15.7 |

`out tok/s` is output tokens over the model's own generation time (pi's `durationMs` sum); the
opencode row has no such figure in its stream, so it is tokens over wall time.

Total wall clock for 3/3 is **456 s for the incumbent against 504 s** for the 27B adapter, but
that is not a fair tie: the 27B decodes **3.9× slower per token** (29–35 vs 7.6–8.7 tok/s) and
only keeps up because it emits about a third of the tokens (3 979 vs 10 962) over fewer turns
(20 vs 47). The incumbent's t2 alone was 23 turns. Decode speed is what a long agentic task
spends, and these three tasks are small.

### 5.3 What each failure actually was

- **opencode ×3** — never a wrong answer, always an unfinished one. t1's transcript: the model
  found the right line at step 8, then failed five edits on indentation
  (`Could not find oldString … must match exactly, including whitespace`), then hallucinated
  `/home/ckindle/Dev/portal-5/...`. The same model on the same task under pi fixed it in 8
  turns. opencode's exact-match `edit` contract plus its longer discovery path at 11.5 tok/s is
  what fails; llama-server's own log shows prompt caching working (~900–4 800 new tokens per
  step) and ~80 s per step spent decoding 800–1 000 tokens.
- **LFM t1** — the model's first move was `find / -path "*tests/unit/test_jarvis_live_fails_r2.py"`
  with no timeout; it never returned and the 900 s cap killed the run. pi's bash tool has no
  default timeout, so a model that does this hangs the lane.
- **LFM t2, TwIL t2** — real attempts that did not find the fix inside the cap (7.6k–14.3k
  output tokens spent, mostly thinking).
- **LFM t3** — fixed it, but kept going (thinking-heavy) past the cap.

## 6. Recommendation

**Keep the incumbent. Do not re-seat the brain.** "Unproven — keep the incumbent" is the honest
reading of this data:

1. The best candidate (`qwen38-27b-pi-lora`, 3/3) ties the incumbent on score. It only matches
   its wall clock (504 s vs 456 s over the three tasks) by emitting a third of the tokens over
   fewer turns, at **3.9× fewer tokens per second** (7.6–8.7 vs 29–35 tok/s) and a hard **32k
   context ceiling** against the incumbent's 128k. Any task that needs more output — which the
   P40 lane rules say is where this box struggles — costs 4× the wall clock, and 32k rules out
   the long-context work the incumbent already does.
2. The card's claims (+25.5 points SWE-bench Pro over base) are BF16, vLLM, B200 measurements.
   Nothing on this card reproduces that; three tasks cannot resolve a ±14-point difference, and
   the GGUF is unevaluated by its own card.
3. The opencode adapter, run under the harness it was trained for, completed **0/3** — so the
   "two harness adapters ready for the lane" claim does not hold on this box.
4. LFM2.5 (1/3) and TwIL (2/3) are trained for data-analysis tasks, and their cards put them
   within noise of their own bases on repository tasks (−5.0 ± 13.9 for LFM, +5.7 ± 16.0 for
   TwIL). They behave exactly as their cards predict here, at 15–60 tok/s.

If the operator wants a 27B dense seat for *quality* work rather than lane work, the honest next
step is a proper paired run of `qwen38-27b-pi-lora` against `qwen3.8:code32k` (its own base, no
adapter) on the same task set — that isolates the adapter, which this brief did not ask for.

## 7. What changed on thebrain

- **No Ollama tag was created** — 0.40.16 refuses `ADAPTER` (section 2). The four candidates
  exist only as llama-server `--alias` ids while a server is running.
- Files added: `/usr/share/ollama/adapters/` 833 MB — four adapter GGUFs, `chat_template.jinja`,
  two Modelfiles.
- Weights pulled: `hf.co/mradermacher/TwIL-8B-GGUF:Q8_0` 9.3 GB (Ollama blob store). Disk
  `693G` used after vs `683G` before (the ~10 G is 9.3 G of TwIL plus 833 MB of adapters).
- Nothing else was installed or upgraded; the incumbent tag, the Ollama unit, the override
  drop-in and the dispatcher are untouched. At the end of the lane no `llama-server` was
  running and the GPU was idle (711 MiB); Ollama is active with no resident model, so the first
  `brain` request loads `qwen3.6-35b-a3b:q3code` exactly as before.
- On this Mac: `~/.pi/agent/models.json` was created (it did not exist) with two providers —
  `p40` → :11434 and `p40local` → :8091 — which is what pi needs to reach the box; no default
  model and no dispatcher entry was changed.

## 8. Reproduce

```bash
# build the kit: parent commit + the fix's own test
git archive be354dacd^ | tar -x -C /tmp/t1 && git show be354dacd:tests/unit/test_jarvis_live_fails_r2.py > /tmp/t1/tests/unit/
# serve a candidate (alias = the tag name in the brief)
llama-server -m <base.gguf> --lora <adapter-F16.gguf> -ngl 99 -c 32768 -fa on -np 1 \
  --host 0.0.0.0 --port 8091 --alias qwen38-27b-pi-lora:ctx32k \
  --temp 0.8 --top-p 1.0 --top-k 0 --min-p 0 -rea off
# run and grade
cd /tmp/t1 && pi --provider p40 --model qwen38-27b-pi-lora:ctx32k --thinking off --print \
  --no-session --mode json --no-skills --no-mcp --no-prompt-templates -nc "<task prompt>"
uv run pytest tests/unit/test_jarvis_live_fails_r2.py -q
```

The exact scripts and per-run logs are in `coding_task/scratch/p40/` (gitignored) —
`run_task.sh`, `run_opencode.sh`, `conform.sh`, `prompts/`, and one `result.json` per run.
