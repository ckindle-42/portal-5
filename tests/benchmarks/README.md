# Portal 5 Benchmarks

## Comprehensive TPS Benchmark

Tests tokens/sec across all models, all workspaces, and all personas on every available backend.

### Prompt Library

Each model/workspace is tested with a category-mapped prompt (~200 tokens output) relevant to its domain. This ensures TPS numbers are comparable within a category — a coding model gets a coding prompt, a security model gets a security prompt, etc.

| Category | Target output | Prompt type |
|---|---|---|
| `general` | ~200 tokens | OSI model layers list (structured factual) |
| `coding` | ~200 tokens | Python merge_intervals function (code generation) |
| `security` | ~200 tokens | SSH brute-force analysis (MITRE ATT&CK structured) |
| `reasoning` | ~200 tokens | ER bottleneck math problem (step-by-step calc) |
| `math` | ~300 tokens | 3-problem set: train meeting, combinatorics, quadratic (symbolic) |
| `creative` | ~200 tokens | Noir detective opening scene (narrative) |
| `vision` | ~200 tokens | Image analysis framework (structured + meta) |

**Mapping (auto-* workspaces — see `WORKSPACE_PROMPT_MAP` in `bench_tps.py`):**
- `auto-coding`, `auto-agentic`, `auto-spl`, `auto-documents` → coding
- `auto-security`, `auto-redteam`, `auto-blueteam` → security
- `auto-reasoning`, `auto-data`, `auto-compliance`, `auto-mistral`, `auto-research` → reasoning
- `auto-math` → reasoning *(+ extra math pass, see below)*
- `auto-creative`, `auto-video`, `auto-music` → creative
- `auto-vision` → vision
- `auto`, `auto-daily`, `auto-audio` → general

**Bench workspaces** route directly to a fixed model and use that model's
primary-capability prompt:
- `bench-devstral-small-2`, `bench-qwen3-coder-next`, `bench-qwen3-coder-30b`,
  `bench-qwen3-coder-next-abliterated`, `bench-llama33-70b`, `bench-glm`,
  `bench-granite41-8b`, `bench-granite41-30b`, `bench-starcoder2`,
  `bench-omnicoder2`, `bench-toolace25`, `bench-nex-n2-mini` → coding
- `bench-phi4`, `bench-phi4-reasoning`, `bench-gptoss`, `bench-laguna`,
  `bench-apriel-nemotron`, `bench-mistral-small32`, `bench-r1-0528-qwen3-8b`,
  `bench-r1-0528-abliterated`, `bench-negentropy`, `bench-foundation-sec`,
  `bench-olmo3-32b` → reasoning
- `bench-phi4-mini-reasoning` → reasoning *(+ extra math pass)*
- `bench-lfm2-moe`, `bench-lfm25-8b`, `bench-lfm25-8b-uncensored`,
  `bench-dolphin8b`, `bench-qwen36-hauhaucs` → creative
- `bench-olmocr2`, `bench-nanonets-ocr2`, `bench-gemma4-e2b`, `bench-gemma4-e4b`,
  `bench-gemma4-e4b-qat` → vision
- `bench-qwen35-abliterated`, `bench-gemma4-12b`, `bench-gemma4-26b-qat`,
  `bench-gemma4-31b-qat`, `bench-gemma4-26b-optiq`, `bench-harness1`,
  `bench-huihui-qwen36-27b`, `bench-huihui-qwen36-35b-a3b` → general
- `bench-qwen36-27b`, `bench-qwen36-27b-mtp`, `bench-qwen36-35b-a3b`,
  `bench-qwen36-27b-ud`, `bench-qwen36-35b-a3b-ud`, `bench-qwen36-27b-optiq` → coding

Speech-only workspaces (`bench-voxtral-realtime`, `bench-voxtral-tts`, `bench-granite-speech`)
are excluded from `WORKSPACE_PROMPT_MAP` by design — the text harness cannot exercise ASR/TTS.

Models are mapped by their Ollama backend group. Personas are mapped by their YAML `category` field.

### Math specialist extra pass

Math-specialist workspaces and models run **both** their primary category prompt AND the
`math` prompt. This produces two result entries per math specialist — one for their normal
domain score (e.g., `auto-math` / `reasoning`) and one for the symbolic math score
(`auto-math:math` / `math`). This makes it possible to compare phi4-mini-reasoning's
math capability against its general reasoning speed in the same run.

Workspaces with an extra math pass: `auto-math`, `bench-phi4-mini-reasoning`,
`bench-phi4-mini`, `bench-phi4`.

Models with an extra math pass (direct mode): those matching `phi4-mini-reasoning`,
`phi4-mini`, `Phi-4-mini` in the model ID.

Quality signals for `math`: `180` (train distance), `11` (11:00 AM meeting time),
`50` (combinatorics team count), `factor`, `-6` (quadratic root), `n = 3`.

### Reasoning model budget

Thinking models emit `<think>` blocks before their response. `REASONING_WORKSPACES` and
`_REASONING_MODEL_PATTERNS` in `bench_tps.py` gate a larger `REASONING_MAX_TOKENS=512`
budget and `enable_thinking=False` suppression so TPS reflects output speed, not CoT overhead.

Covered workspaces: `bench-laguna`, `bench-phi4-reasoning`, `bench-phi4-mini-reasoning`,
`bench-foundation-sec`, `bench-r1-0528-qwen3-8b`, `bench-r1-0528-abliterated`,
`auto-mistral`, `auto-reasoning`, `auto-math`, `auto-security`, `auto-redteam`.

### Usage
```bash
python3 tests/benchmarks/bench_tps.py                         # everything, 5 runs
python3 tests/benchmarks/bench_tps.py --runs 1                # single run (faster)
python3 tests/benchmarks/bench_tps.py --mode direct           # backends only
python3 tests/benchmarks/bench_tps.py --mode pipeline         # workspaces only
python3 tests/benchmarks/bench_tps.py --mode personas         # personas only
python3 tests/benchmarks/bench_tps.py --model phi4-mini       # filter by model substring
python3 tests/benchmarks/bench_tps.py --workspace auto-coding # single workspace
python3 tests/benchmarks/bench_tps.py --persona cybersecurity # filter personas
python3 tests/benchmarks/bench_tps.py --prompt "say hello"    # override all prompts
python3 tests/benchmarks/bench_tps.py --output results.json   # custom output
python3 tests/benchmarks/bench_tps.py --dry-run               # show plan
python3 tests/benchmarks/bench_tps.py --cooldown 5            # 5s gap between models
python3 tests/benchmarks/bench_tps.py --order config          # backends.yaml order
```

### Memory Management

Models are tested **one at a time** (sequential, blocking HTTP). Memory is managed between tests:

- **Ollama**: each model is force-unloaded via `keep_alive=0` after its test completes. Sends an empty generate request with `keep_alive: 0` which tells Ollama to immediately release the model from unified memory.
- **`--cooldown N`** (default: 10): seconds to wait between model tests for Metal memory reclamation. Increase to 15-20s when testing 40GB+ models back-to-back.
- **`--order size`** (default): sorts models by estimated memory footprint (smallest first). Sizes are parsed from `backends.yaml` comments. This ensures a 70B test failure doesn't waste time after small models already passed.
- **`--order config`**: preserves the original `backends.yaml` ordering.

### What Gets Tested
Counts are derived at run time from `config/backends.yaml` + `config/personas/`
and reported in the script's startup banner. The current catalog (HEAD, 2026-06-10) is
**73 workspaces** (20 `auto-*` + 52 `bench-*` + 1 `tools-specialist`) and **~137 personas**.
All inference is Ollama — the MLX inference proxy was retired in commit `3a0c58e`.

Undownloaded Ollama models are reported with `available: false` in the results — not silently skipped.

### Output
JSON file at `tests/benchmarks/results/bench_tps_<UTC>.json` (default; overridable with `--output`).

```bash
jq '.results[] | select(.path=="direct") | {model, avg_tps, prompt_category}' tests/benchmarks/results/bench_tps_*.json
jq '.results[] | select(.path=="pipeline") | {workspace, avg_tps, prompt_category}' tests/benchmarks/results/bench_tps_*.json
jq '.results[] | select(.path=="persona") | {persona_slug, workspace_model, avg_tps}' tests/benchmarks/results/bench_tps_*.json
jq '.results[] | select(.available==false) | {model, backend, error}' tests/benchmarks/results/bench_tps_*.json
```

---

## Full Bench Cycle (run + update dashboard)

After a bench run, regenerate the Grafana benchmark dashboard from the results. An agent
running a full bench cycle should execute both steps:

```bash
# Step 1 — run the benchmark (standard baseline: all modes, 5 runs, size order)
python3 tests/benchmarks/bench_tps.py --mode all --order size --runs 5 --cooldown 10

# Step 2 — find the results file just created (latest by timestamp)
RESULTS=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)

# Step 3 — regenerate the Grafana dashboard
python3 scripts/update_grafana_benchmarks.py --input "$RESULTS"

# Step 4 — commit both results file and updated dashboard
git add "$RESULTS" config/grafana/dashboards/portal5_benchmarks.json
git commit -m "bench: TPS baseline <date> — <peak_tps> t/s peak, <models> models"
```

For a targeted re-bench (single workspace or model), skip step 4 unless it's a committed baseline:
```bash
# Single workspace
python3 tests/benchmarks/bench_tps.py --workspace bench-phi4-mini-reasoning --runs 3

# Single model across all paths
python3 tests/benchmarks/bench_tps.py --model phi4-mini-reasoning --runs 3

# Then update dashboard with the new partial results
python3 scripts/update_grafana_benchmarks.py --input tests/benchmarks/results/bench_tps_<timestamp>.json
```

The Grafana dashboard JSON lives at `config/grafana/dashboards/portal5_benchmarks.json` — it is
a static snapshot, not a live Prometheus board. It is only current if regenerated after the
most recent bench run. The live metrics dashboard (`portal5_overview.json`) is always current
via Prometheus scrape.

---

## Grafana Dashboards

| Dashboard | File | Data source | Freshness |
|---|---|---|---|
| Portal 5 Overview | `config/grafana/dashboards/portal5_overview.json` | Prometheus (live) | Always current |
| Benchmarks | `config/grafana/dashboards/portal5_benchmarks.json` | Static HTML | Regenerate after each bench run |
