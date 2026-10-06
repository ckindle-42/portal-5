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

### P2 security review (automated, post-commit) — dispositions
- Engine inherited the server env (incl. `OWUI_API_KEY`) while running model-authored code: **fixed** — engine now spawns with an explicit allowlist (`_ENGINE_ENV_ALLOWLIST`), unit-tested.
- `/tools/cad_*` routes unauthenticated: **acknowledged, unchanged** — same convention as every fleet MCP `/tools/*` route (host port bound to 127.0.0.1; reachable only from the compose network). The engine additionally rejects `os`/`subprocess`/socket/pathlib imports in executed code (verified live: `import os` -> SecurityError). Residual: the parent process still holds `OWUI_API_KEY` in its own environment.

## P3 — generate_part: same IR, BREP backend: PASS
- Goldens first: 82 IR inputs (the 10 CORPUS items + one per face/feature/edge/CSG/parameter variant, all 6 faces) captured from unchanged HEAD into `tests/data/cad_scad_golden/` (commit d4805a2e). After the split, **all 82 emit byte-identical SCAD** (`tests/unit/test_scad_golden.py`).
- Split: `part_plan.py` (EmitError, validation, parameters, face frames, pattern expansion, plan dataclasses, `plan_part`) — moved mechanically, not rewritten; `scad_emitter.py` is now a thin `render_scad` backend that re-exports the public names; `b123d_emitter.py` is the BREP backend. Pocket/rib/shell cutters and hole/standoff positions are resolved once in the plan.
- Parity (container, OpenSCAD nightly Manifold; volumes mm^3, genus b3d/scad):

| part | vol b3d | vol scad | dV % | genus |
|---|---|---|---|---|
| plain_plate | 6000.0 | 6000.0 | 0.00 | 0/0 |
| grommet_plate | 8607.9 | 8627.5 | -0.23 | 3/3 |
| drilled_standoff | 8345.4 | 8344.6 | 0.01 | 0/0 |
| open_enclosure | 13632.0 | 13632.0 | 0.00 | 0/0 |
| mounting_bracket | 2880.0 | 2880.0 | 0.00 | 0/0 |
| vented_panel | 3600.0 | 3600.0 | 0.00 | 5/5 |
| cylindrical_adapter | 7687.4 | 7668.7 | 0.24 | 1/1 |
| chamfered_block | 6926.5 | 6927.7 | -0.02 | 0/0 |
| filleted_block | 6942.9 | 6907.6 | 0.51 | 0/0 |
| gearish_disc | 5765.6 | 5751.5 | 0.24 | 8/8 |

  Extents match the corpus expectation within 0.05 mm; 96 emitter+golden tests pass inside the arm64 container too. Tolerances were not loosened.
- Sweep of all 82 golden inputs through the BREP backend: 80 build to one valid solid. The 2 exceptions are declared **kernel_gap** (error points the model at `cad_build`): Tier-B `linear_extrude`/`rotate_extrude` (IR has no 2D primitives, so the SCAD form is also degenerate) and a base carrying both fillets and chamfers (second op would target the first op's blended edges). To record in KNOWN_LIMITATIONS (P6).
- Semantics note: the SCAD fillet envelope always rounds a box's vertical edges (any `edges` value); the BREP backend matches that for fillets, not for chamfers. The schema's `edges` enum is `all|top|bottom` (no `vertical`).
- Mesh artifact: OCC tessellation of an all-edges-filleted box leaves 8 zero-area sliver triangles in the STL, so trimesh reports it non-watertight although the BREP solid is valid. The parity test drops degenerate faces; the sealed grader does not, so a fillet-all part could grade INVALID from the engine's STL. Watch in P5.
- `generate_part` tool + route + manifest entry; `sync_cad_geometry_schema.py` now keeps one schema for `generate_scad` and `generate_part` (parity test extended). Live: `grommet_plate` IR -> `/tools/generate_part` -> step/stl/png/script URLs, graded by `grade_mesh` = **PASS** (volume 8609.7, genus 3).

### P3 security review (automated, post-commit) — disposition
- Parameter names / part name were interpolated into the generated build123d script: **fixed** — parameter names must match `^[A-Za-z_][A-Za-z0-9_]{0,63}$` (schema `propertyNames` + enforced in `resolve_parameters`, so both backends reject it), and comment text goes through an escaping helper (`repr`) so newlines/CR/U+2028 cannot end the comment. Tests: `test_user_strings_cannot_inject_script_lines`, `test_parameter_names_must_be_identifiers`. (Not a new privilege — `cad_build` already runs model-authored code in the import-restricted engine — but the IR path should not be a bypass of the structured-input contract.)
- Test change: `test_auto_cad_prompt_example_validates_against_schema` extracted a JSON example from the old prompt; the P4-A prompt has none, so it now validates the schema's own `examples`.
