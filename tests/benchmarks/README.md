# Portal 5 — Benchmarks

Performance benchmarks for comparing MLX (Apple Silicon) vs Ollama (GGUF) inference backends.

## bench_mlx_vs_ollama.py

Compares streaming inference performance between the MLX server (`mlx_lm.server`) and Ollama on identical prompts.

### Prerequisites

Both backends must be running:

```bash
# Terminal 1: Start MLX server
~/.portal5/mlx/start.sh

# Terminal 2: Start Ollama
ollama serve

# Verify both are up
curl -s http://localhost:8081/v1/models | python3 -m json.tool
curl -s http://localhost:11434/v1/models | python3 -m json.tool
```

### Usage

```bash
# Default run: 3 iterations, Qwen3-Coder-Next-4bit (MLX) vs qwen3.5:9b (Ollama)
python3 tests/benchmarks/bench_mlx_vs_ollama.py

# Custom model pair
python3 tests/benchmarks/bench_mlx_vs_ollama.py \
    --mlx-model mlx-community/Llama-3.2-3B-Instruct-4bit \
    --ollama-model llama3.2:3b-instruct-q4_K_M

# More iterations for stable numbers
python3 tests/benchmarks/bench_mlx_vs_ollama.py --runs 5 --max-tokens 256

# Non-streaming mode (measures end-to-end latency, not TTFT)
python3 tests/benchmarks/bench_mlx_vs_ollama.py --no-stream
```

### Output

```
==================================================
BENCHMARK RESULTS
==================================================
  Metric                     MLX        Ollama   Speedup
----------------------------------------------------------
  Avg TTFT (ms)              142.3        387.1
  Min TTFT (ms)              118.7        341.2
  Max TTFT (ms)              201.4        512.8
  Avg tokens/sec             42.3         28.7       1.47x
  Avg latency (s)             8.234       12.891
  Runs                            3             3
----------------------------------------------------------
  MLX model:    mlx-community/Qwen3-Coder-Next-4bit
  Ollama model: qwen3.5:9b
==================================================

  MLX is 1.47x faster than Ollama on this hardware.
```

### Metrics Explained

| Metric | Description |
|--------|-------------|
| **TTFT** | Time To First Token — how quickly the model starts responding (critical for UX) |
| **tokens/sec (t/s)** | Throughput — sustained generation speed after warm-up |
| **Avg latency** | End-to-end time from request to last token (streaming) |
| **Speedup** | MLX t/s ÷ Ollama t/s — relative speedup ratio |

### Interpreting Results

- **TTFT variance** is typically larger than t/s variance — use `--runs 5` for TTFT
- MLX advantage is most pronounced on **streaming, short-to-medium responses**
- Ollama GGUF may match or exceed MLX on **long generations** where compute-bound t/s dominates
- On **M3/M4 with unified memory**, MLX typically shows 1.3–2× speedup
- On **M1/M2**, MLX advantage is smaller (no unified memory)

### Adding Custom Prompts

Edit `BENCHMARK_PROMPTS` in the script or pass a single prompt:

```bash
python3 tests/benchmarks/bench_mlx_vs_ollama.py \
    --prompt "Write a comprehensive test plan for a login form"
```
