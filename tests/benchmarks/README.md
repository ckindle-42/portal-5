# Portal 5 Benchmarks

## MLX vs Ollama

Measures tokens/sec and request latency for matched model pairs.

### Requirements
- MLX running: `MLX_MODEL=mlx-community/Llama-3.2-3B-Instruct-8bit ~/.portal5/mlx/start.sh`
- Ollama running with: `ollama pull hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF`

### Run
```bash
python3 tests/benchmarks/bench_mlx_vs_ollama.py
python3 tests/benchmarks/bench_mlx_vs_ollama.py --runs 5
```

### Interpreting Results
- CLAUDE.md documents 20-40% MLX advantage on M4 hardware
- Run 3+ times for stable averages (first run may be slower due to model loading)
- Cold vs warm: restart mlx_lm.server between runs for cold-cache numbers
