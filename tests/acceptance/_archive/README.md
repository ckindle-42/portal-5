# Archived acceptance scenarios

These scenarios tested the MLX inference proxy (:8081/:18081/:18082)
retired in commit 3a0c58e. They are kept for recoverability, not run.

| Scenario | Tested | Why archived |
|---|---|---|
| s20_mlx | MLX proxy /health + /v1/models | proxy deleted |
| s22_admission_control | MLX admission control 503 | proxy deleted |
| s03b_routing_mlx | mlx_only workspace routing | mlx_only flag removed |
| s11_personas_mlx | MLX-backed persona smoke | personas now Ollama-backed |
| s24_specialist_mlx | Foundation-Sec / ToolACE in MLX | see KNOWN_LIMITATIONS § Model Parity |
