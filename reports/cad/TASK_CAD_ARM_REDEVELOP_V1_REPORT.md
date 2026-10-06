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

## P1 — dedicated arm64 CAD image: PASS
- OpenSCAD branch: **nightly-manifold**. OBS `home:t-paul/Debian_13/arm64/` serves `openscad-nightly_20261005T003339...arm64.deb`; installed via signed-by keyring. `openscad-nightly --version` = `2026.10.05.nightly`; `--backend` lists CGAL/Manifold (Manifold default).
- Arch: image `Architecture`=arm64; `uname -m`=aarch64; OCP `.so` = `OCP.cpython-311-aarch64-linux-gnu.so`; build123d 0.11.1, vtk 9.7.1, build123d-mcp 0.3.90.
- Oracles in container: 8/8 PASS (machine=aarch64 system=Linux).
- Manifold vs CGAL (64-sphere difference on 60x60x20 cube, same binary): CGAL 68.1 s, Manifold 0.53 s.
- `PYOPENGL_PLATFORM=osmesa` kept in compose; `VTK_DEFAULT_OPENGL_WINDOW` not added (no VTK render path exercised until P2).
- Dockerfile.mcp: removed `openscad`, `libosmesa6`, CAD pip layers, micromamba block. Grep of portal/portal_mcp/portal_channels outside portal/modules/cad for trimesh|pyrender|matplotlib|stl|numpy_stl|jsonschema imports: none.
- capabilities.py: conda hooks removed; probes added (`openscad_bin/version/backend`, `build123d_mcp`, `arch`; `platform` key renamed, nothing read it); `engine` added via uncached `cad_status()` (served by `/capabilities`).
- Fact unit `unit-fact-dockerfile-index` updated (8 Dockerfiles; check BS claim).
- Unit tests `-k "cad or scad or mesh"`: 77 passed.

## P2 — build123d engine bridge on :8926: PASS
- Payloads P2-A/B/C written (checksums match); fragment merged into the cad_render manifest (4 -> 10 entries) and deleted. `sync_cad_geometry_schema.py` preserves `cad_*` entries (no script change needed).
- Wired: 6 POST routes via factory, `start_engine` in `__main__`, `--backend=manifold` when `CAD_OPENSCAD_BACKEND=manifold`, docstring updated.
- Live: `/capabilities` -> engine:true, build123d:true, arch:aarch64, openscad_backend:manifold. Tools list shows the 6 cad_* tools.
- plate_4holes via cad_build -> cad_finalize: ok, printability 0 findings, step/stl/script/png URLs published through OWUI (`/api/v1/files/...`); STL graded PASS by `grade_mesh`.
- Pipeline `/admin/refresh-tools`: 153 tools registered, includes cad_build/execute/measure/find_holes/render/finalize.
- mypy: 161 pre-existing errors elsewhere in portal/, unchanged by this phase.
