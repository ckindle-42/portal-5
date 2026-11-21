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

(filled in as the runs land)
