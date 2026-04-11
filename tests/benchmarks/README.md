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
| `creative` | ~200 tokens | Noir detective opening scene (narrative) |
| `vision` | ~200 tokens | Image analysis framework (structured + meta) |

**Mapping:**
- `auto-coding`, `auto-agentic`, `auto-spl`, `auto-documents` → coding
- `auto-security`, `auto-redteam`, `auto-blueteam` → security
- `auto-reasoning`, `auto-data`, `auto-compliance`, `auto-mistral` → reasoning
- `auto-creative`, `auto-video`, `auto-music` → creative
- `auto-vision` → vision
- `auto`, `auto-research` → general

Ollama models are mapped by their backend group. MLX models are mapped by name pattern. Personas are mapped by their YAML `category` field.

### Usage
```bash
python3 tests/benchmarks/bench_tps.py                         # everything, 3 runs
python3 tests/benchmarks/bench_tps.py --runs 1                # single run (faster)
python3 tests/benchmarks/bench_tps.py --mode direct           # backends only
python3 tests/benchmarks/bench_tps.py --mode pipeline         # workspaces only
python3 tests/benchmarks/bench_tps.py --mode personas         # personas only
python3 tests/benchmarks/bench_tps.py --model dolphin-llama3  # filter by model substring
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

- **Ollama**: each model is force-unloaded via `keep_alive=0` after its test completes. This uses the same pattern as the MLX proxy's `_evict_ollama_models_for_big_model()` — sends an empty generate request with `keep_alive: 0` which tells Ollama to immediately release the model from unified memory.
- **MLX proxy**: the proxy handles model switching internally (admission control, single-model-at-a-time). A cooldown period between tests lets the proxy fully switch and release GPU memory.
- **`--cooldown N`** (default: 3): seconds to wait between model tests for memory reclamation. Increase to 10-15s on memory-constrained machines or when testing 40GB+ models back-to-back.
- **`--order size`** (default): sorts models by estimated memory footprint (smallest first). MLX sizes come from the proxy's `MODEL_MEMORY` dict. Ollama sizes are parsed from `backends.yaml` comments. This ensures a 70B test failure doesn't waste time after small models already passed.
- **`--order config`**: preserves the original `backends.yaml` ordering (all MLX first, then all Ollama groups).

### What Gets Tested
- **22 MLX models** from `config/backends.yaml`
- **23 unique Ollama models** across 6 backend groups from `config/backends.yaml`
- **17 workspaces** from `config/backends.yaml` `workspace_routing`
- **44 personas** from `config/personas/*.yaml`

Undownloaded Ollama models and unregistered MLX models are reported as `MISSING` in the results — not silently skipped.

### Output
JSON file at `/tmp/bench_tps_results.json` with per-run data. Use `jq` for filtering:
```bash
jq '.results[] | select(.backend=="mlx") | {model, avg_tps, prompt_category}' /tmp/bench_tps_results.json
jq '.results[] | select(.path=="pipeline") | {workspace, avg_tps, prompt_category}' /tmp/bench_tps_results.json
jq '.results[] | select(.path=="persona") | {persona_slug, workspace_model, avg_tps}' /tmp/bench_tps_results.json
jq '.results[] | select(.available==false) | {model, backend, error}' /tmp/bench_tps_results.json
```

---

## MLX vs Ollama (single pair comparison)

Measures tokens/sec for one matched model pair. Uses the same prompt for both.

### Requirements
- MLX running with Llama-3.2-3B-Instruct-8bit
- Ollama running with hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF

### Run
```bash
python3 tests/benchmarks/bench_mlx_vs_ollama.py
python3 tests/benchmarks/bench_mlx_vs_ollama.py --runs 5
```
