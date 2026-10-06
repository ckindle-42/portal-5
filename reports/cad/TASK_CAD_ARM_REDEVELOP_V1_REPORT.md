# TASK_CAD_ARM_REDEVELOP_V1 — run report

## Phase table
| Phase | Status | Evidence |
|---|---|---|
| P0 | PASS | arch gate; build123d 0.11.1 arm64; 8/8 oracles PASS (arm64 Darwin); B0 baseline below |

## P0 evidence
- HEAD at start `3b9f9d8b` (task authored against `d4cac6ec`); all 9 anchors matched once.
- Host arm64; Docker arch arm64; ollama arm64; OCP `.so` Mach-O arm64; build123d-mcp 0.3.90.
- Deviation: cad extra pins carry `; python_version >= '3.11'` (build123d-mcp needs >=3.11; project floor is 3.10, so `uv lock` failed without it).
- `lib3mf` on macOS is a universal2 wheel (includes arm64); linux/aarch64 uses `py-lib3mf` by marker.
- Sync used `uv sync --all-extras` (repo norm per scripts/ci_local.sh); plain `--extra cad` would uninstall other extras.
- B0 `auto-cad` block (rollback target): `reports/cad/B0_auto-cad_block.yaml`.

## B0 (auto-cad, qwen3-coder:30b-a3b-q4_K_M-ctx16k, 3 reps x 8 tasks)
mean 0.688 · PASS rate 0.375 · validity 0.958 · median 34.0 s.
PASS 3/3: plate_4holes, grommet_plate, countersunk_plate. 0/3: enclosure, l_bracket, flanged_bushing, hex_standoff, spur_gear.
Artifacts: `tests/benchmarks/results/cad_gauntlet_v2_B0_20261006T160659Z.{json,md}`.
