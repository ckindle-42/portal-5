# REPORT — P40 harness-adapter seats (for the operator's Wednesday report)

Lane `lane/omlx081-intake`, 2026-11-21. Everything marked **measured** was executed on
thebrain (Tesla P40, 24 GB, driver 580.178.04) or on this Mac against thebrain over HTTP;
everything marked **read** came from the source named with it. The Mac's Portal stack, its
Ollama and its oMLX were not touched.

## 0. Status of this file

Work in progress — appended as each candidate is built and run. Section 5 is the results
table; it is complete only when every row is filled from a real run.

## 1. Baseline, measured on thebrain

| Fact | Value |
| --- | --- |
| GPU | Tesla P40, 24 576 MiB, driver 580.178.04 |
| Ollama | 0.40.16 |
| Ollama env | `OLLAMA_NUM_PARALLEL=4`, `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_FLASH_ATTENTION=1` |
| Incumbent `qwen3.6-35b-a3b:q3code` | 17 GB, `num_ctx 131072`, resident at 23 651 MiB |
| Disk | 1.1 T free on `/` |

## 2. Finding 1 — Ollama 0.40.16 cannot build a LoRA tag at all

The brief's first two candidates are Modelfiles with `ADAPTER`, i.e. `ollama create`.
On this box that is not a build that fails on memory or on the adapter format — it is
refused outright:

```
$ sudo -u ollama ollama create qwen38-27b-pi-lora:ctx32k -f /usr/share/ollama/adapters/qwen38-27b-pi-lora.modelfile
Error: LoRA adapters are no longer supported
```

The binary carries two messages: `LoRA adapters are deprecated and will be removed in a
future release` and `LoRA adapters are deprecated; the adapter layer is carried over but new
adapters cannot be created`. So a tag that already has an adapter keeps working, and no new
one can be made. `ollama create --help` (0.40.16) offers `--combine`, `--draft-quantize`,
`--quantize` and no adapter flag.

Consequence: **none of the four candidates can be an Ollama tag on this box.** They are
served instead by the lane's own llama.cpp build (`~/llama.cpp/build/bin/llama-server`,
0.9.0-dev build 12138 f7b41cca4, CUDA), which supports `--lora` — the path both
harness-hub cards themselves prescribe. The served `--alias` is the brief's tag name, so the
harness-visible model id is unchanged:

```
llama-server -m <base.gguf> --lora <adapter-F16.gguf> -ngl 99 -c 32768 -fa on -np 1 \
  --host 0.0.0.0 --port 8091 --alias qwen38-27b-pi-lora:ctx32k \
  --temp 0.8 --top-p 1.0 --top-k 0 --min-p 0 -rea off
```

`--temp/--top-p/--top-k/--min-p` bake the card's sampling exactly as `PARAMETER` would in a
Modelfile; `-rea off` is the card's "thinking off" (the Qwen3.8 template defaults to
*medium* thinking).

Downgrading Ollama was considered and rejected: 0.40.16 is what the rest of the lane runs,
the incumbent tag is resident in it, and the brief says leave thebrain's default seat and
dispatcher alone.

## 3. Setup proof per candidate

Common: base GGUFs are read straight from Ollama's blob store, so no second copy of any
weights exists on disk. Adapters live in `/usr/share/ollama/adapters/` (world-readable;
`/home/jarvis` is mode 750 and not reachable by the `ollama` user).

### 3.1 `qwen38-27b-pi-lora:ctx32k` — measured

| Item | Evidence |
| --- | --- |
| Base | Ollama blob `sha256-f5f1dd8920d4…` = `qwen3.8:code32k`, `ollama show`: architecture `qwen35`, 27.3 B, `Q4_K_M`, ctx 262 144, GGUF `general.name = "Qwen3.8 27B 0814"` |
| Adapter | `Qwen3.8-27B-pi-lora-F16.gguf`, 318 802 304 B, `/lora-adapters` → `scale 1.0` |
| VRAM at load, ctx 32768 | **18 741 MiB / 24 576** (`nvidia-smi` with the model loaded) |
| Sampling served | `/props` → `temperature 0.8, top_p 1.0, top_k 0, min_p 0.0`, `n_ctx 32768` |
| Chat template renders | `"Reply with the single word OK."` → `content "OK"`, `finish_reason stop` |
| Thinking state | `reasoning_content: null` (card: thinking off) |
| Tool call parses | `finish_reason "tool_calls"`, one `get_weather` with `{"location":"Little Rock, AR"}` |
| Unused tensors | `blk.64.*` (the MTP/nextn head) ignored — llama.cpp does not use the draft head |

### 3.2 Measured throughput on the card (decides the whole recommendation)

From the llama-server timings on the Qwen3.8-27B qwen35 Q4_K_M base:

```
prompt eval time = 5345.70 ms / 797 tokens (149.09 tokens per second)
       eval time = 101634.70 ms / 1170 tokens (11.50 tokens per second)
```

**~11.5 tok/s decode, ~150 tok/s prefill** for a dense 27B at 32k context on the P40.
Prefill dominates an agent turn: a 20k-token context costs ~130 s before the first token.
A 3B-active MoE (the incumbent) prefills and decodes an order of magnitude faster, which
is the P40's whole design point.


## 4. Task set (real, from this repo's git history)
Three small fixes that already landed here, replayed on their parent commit with only the
fix's own test applied. Each kit starts as a clean `git init` + one commit; grading is the
real pytest file, run after the harness stops.

| Task | Base commit | Test | Fails before / passes after |
| --- | --- | --- | --- |
| t1 | `be354dacd^` | `tests/unit/test_jarvis_live_fails_r2.py` | 1 failed → 24 passed |
| t2 | `04ecd3e38^` | `tests/unit/test_timing_instrument.py` | 1 failed → 10 passed |
| t3 | `033fe18cf^` | `tests/unit/test_admin_reclaim_idle.py` (from `542c3109d`) | 4 failed → 12 passed |

Harness baseline, identical for every model and every task: `pi 1.5.2`, `--thinking off
--print --no-session --mode json --no-skills --no-mcp --no-prompt-templates -nc`, provider
`openai-completions`, 900 s wall cap, cwd = the task kit, prompt = the bug statement only.

## 5. Results

### 5.1 Harness runs (pass = the fix's own pytest file green after the run)

| Seat | Harness | t1 | t2 | t3 | Turns | Wall | tok/s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `qwen3.6-35b-a3b:q3code` (incumbent, Ollama) | pi | — | — | — | — | — | — |
| `qwen38-27b-pi-lora:ctx32k` (llama-server) | pi | **pass** 151 s / 8 turns | **pass** 197 s / 5 turns | **pass** 156 s / 7 turns | 8/5/7 | 504 s | 7.6–8.7 |
| `qwen38-27b-opencode-lora:ctx32k` (llama-server) | opencode | **fail** (timeout 1800 s, 16 steps, 0 edits) | pending | pending | 16 | 1800 s | 0.92 |
| `lfm2.5-24b-a2b-pi-v2:ctx32k` (llama-server) | pi | pending | pending | pending | | | |
| `twil-8b-pi:ctx32k` (llama-server) | pi | pending | pending | pending | | | |

`tok/s` is output tokens over the model's own generation time (pi's `durationMs` sum), so it
excludes grading and file I/O.

### 5.2 What the opencode run actually did (t1)

16 steps, 16 tool calls, 1 660 output tokens, no edit applied, killed at the 1 800 s cap.
The transcript shows the model finding the right line at step 8 and then failing five edits
in a row on indentation:

```
TEXT The cap notice at line 527 includes the raw `outcome.get("result")` — that's the report. Apply `user_answer()` to it.
TOOL edit error | Could not find oldString … It must match exactly, including whitespace and indentation.
…
TOOL edit error | File not found: /home/ckindle/Dev/portal-5/portal/modules/orchestration/personal_runner.py
```

The same model on the same task under pi fixed it in 8 turns. So the adapter's tool calls are
fine; what fails here is opencode's exact-match `edit` contract (the model reproduces the line
with the wrong leading indentation) plus the number of round trips opencode spends on
discovery at 11.5 tok/s.

