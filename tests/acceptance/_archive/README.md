# Archived acceptance scenarios

The MLX-proxy scenarios that previously lived here (s20_mlx, s22_admission_control,
s03b_routing_mlx, s11_personas_mlx, s24_specialist_mlx) tested the MLX inference
proxy (:8081/:18081/:18082) retired in commit 3a0c58e. The archived copies were
deleted in the MLX test-layer sweep (TASK_MLX_TEST_SWEEP_V1) — they carried
unresolved imports and the proxy they tested no longer exists.

Recover any of them from git history at `476de27` or earlier:

    git show 476de27:tests/acceptance/_archive/s20_mlx.py
